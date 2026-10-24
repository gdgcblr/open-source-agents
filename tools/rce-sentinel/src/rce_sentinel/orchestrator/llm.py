"""Provider adapter. One OpenAI-compatible code path covers Ollama, Gemini, DeepSeek, Kimi,
GLM, and OpenRouter. LLM calls never get tools. MockProvider makes everything run offline."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from rce_sentinel.orchestrator.prompts import CAVEMAN_MARKER, approx_tokens

TIERS = ("tier1", "tier2", "tier3")


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str
    family: str
    tier: str
    price_in: float
    price_out: float
    price_cached_in: float
    context_tokens: int = 128_000
    quota_tokens: int | None = None  # per-run token quota; after it the router switches model

    def cost(self, tokens_in: int, tokens_out: int, cached: int = 0) -> float:
        fresh = max(tokens_in - cached, 0)
        return (fresh * self.price_in + cached * self.price_cached_in
                + tokens_out * self.price_out) / 1_000_000


@dataclass
class LLMResult:
    text: str
    tokens_in: int
    tokens_out: int
    cached_tokens: int
    latency_ms: float
    model: str


class Provider(Protocol):
    def complete(self, spec: ModelSpec, system: str, user: str, *, max_tokens: int,
                 timeout: float, prefix_tokens: int = 0, prefix_warm: bool = False,
                 schema: dict[str, Any] | None = None) -> LLMResult: ...


def parse_quotas(raw: str) -> dict[str, int]:
    """'apple-foundationmodel=2000,qwen2.5:3b=5000' -> {model id: tokens per run}."""
    out: dict[str, int] = {}
    for part in filter(None, (p.strip() for p in raw.split(","))):
        model, _, n = part.rpartition("=")
        if model and n.isdigit():
            out[model] = int(n)
    return out


def inline_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema with $ref/$defs inlined, as constrained decoders need."""
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].rsplit("/", 1)[-1]])
            out = {k: walk(v) for k, v in node.items() if k not in {"title", "default"}}
            if out.get("type") == "object":
                out.setdefault("additionalProperties", False)
            return out
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(raw)  # type: ignore[no-any-return]


class ModelRegistry:
    def __init__(self, models_cfg: dict[str, Any], mode: str):
        self.cfg = models_cfg
        self.mode = mode
        self.providers: dict[str, Any] = models_cfg.get("providers", {})
        quotas = parse_quotas(os.environ.get("RCE_SENTINEL_QUOTA", ""))
        self.all: dict[str, list[ModelSpec]] = {
            tier: [ModelSpec(id=m["id"], provider=m["provider"], family=m["family"], tier=tier,
                             price_in=float(m["price_in"]), price_out=float(m["price_out"]),
                             price_cached_in=float(m.get("price_cached_in", m["price_in"])),
                             context_tokens=int(m.get("context_tokens", 128_000)),
                             quota_tokens=quotas.get(m["id"], m.get("quota_tokens")))
                   for m in models_cfg.get("tiers", {}).get(tier, [])]
            for tier in TIERS
        }
        self._local_up: dict[str, set[str]] = {}
        self._down: set[str] = set()
        self.down_status: dict[str, int] = {}

    def base_url(self, provider: str) -> str:
        p = self.providers[provider]
        return (os.environ.get(p.get("base_url_env", "")) or p["base_url"]).rstrip("/")

    def _local_models(self, provider: str) -> set[str]:
        """Model ids a local server can serve now, probed once per run.

        apfel: /health must report model_available. Every server must list the model in
        /v1/models, so apfel on Ollama's port is never mistaken for Ollama.
        """
        if provider not in self._local_up:
            p = self.providers[provider]
            base = self.base_url(provider)
            ids: set[str] = set()
            try:
                healthy = True
                if health := p.get("health"):
                    data = httpx.get(base.removesuffix("/v1") + health, timeout=0.5).json()
                    healthy = bool(data.get("model_available"))
                if healthy:
                    listing = httpx.get(base + "/models", timeout=0.5).json()
                    ids = {m.get("id", "") for m in listing.get("data", [])}
            except (httpx.HTTPError, ValueError, AttributeError):
                ids = set()
            self._local_up[provider] = ids
        return self._local_up[provider]

    def mark_down(self, spec: ModelSpec, status: int = 401) -> None:
        """Stop offering a model for the rest of the run (401 not signed in, 402 plan)."""
        self._down.add(spec.id)
        self.down_status[spec.id] = status

    def is_down(self, spec: ModelSpec) -> bool:
        return spec.id in self._down

    def is_real(self, spec: ModelSpec) -> bool:
        """A real endpoint can serve this model right now."""
        if spec.id in self._down:
            return False
        p = self.providers.get(spec.provider, {})
        if p.get("local"):
            return spec.id in self._local_models(spec.provider)
        return bool(os.environ.get(p.get("api_key_env", "")))

    def is_available(self, spec: ModelSpec) -> bool:
        if spec.id in self._down:
            return False
        if self.mode in {"mock", "hybrid"}:
            return True
        if self.mode == "off":
            return False
        return self.is_real(spec)

    def simulated(self, spec: ModelSpec) -> bool:
        return self.mode == "mock" or (self.mode == "hybrid" and not self.is_real(spec))

    def counts_as_evidence(self, spec: ModelSpec) -> bool:
        """In hybrid mode a mock stands in for a model that is down, so its opinion is not
        evidence. In pure mock mode (offline tests and demos) every model is a mock by design."""
        return not (self.mode == "hybrid" and self.simulated(spec))

    def label(self, spec: ModelSpec) -> str:
        return f"{spec.id} (mock)" if self.simulated(spec) else spec.id

    def available(self, tier: str) -> list[ModelSpec]:
        return [m for m in self.all.get(tier, []) if self.is_available(m)]

    def any_available(self) -> bool:
        return any(self.available(t) for t in TIERS)

    def baseline(self) -> ModelSpec:
        target = self.cfg.get("baseline_model")
        for tier in reversed(TIERS):
            for m in self.all[tier]:
                if m.id == target:
                    return m
        return self.all["tier3"][0]


class OpenAICompatProvider:
    RETRY_STATUS = frozenset({429, 503})  # rate limited, or apfel still loading assets

    def __init__(self, registry: ModelRegistry, retries: int = 2):
        self.registry = registry
        self.retries = retries

    @staticmethod
    def _response_format(provider: dict[str, Any], schema: dict[str, Any] | None
                         ) -> dict[str, Any]:
        """Constrained decoding when the provider supports it: the reply always has the
        right shape, which small local models otherwise get wrong."""
        if schema and provider.get("json_schema"):
            return {"type": "json_schema",
                    "json_schema": {"name": "reply", "strict": True, "schema": schema}}
        return {"type": "json_object"}

    def _post(self, url: str, body: dict[str, Any], headers: dict[str, str],
              timeout: float) -> httpx.Response:
        deadline = time.monotonic() + timeout
        for attempt in range(self.retries + 1):
            left = max(0.5, deadline - time.monotonic())
            resp = httpx.post(url, json=body, headers=headers, timeout=left,
                              follow_redirects=False)
            if resp.status_code not in self.RETRY_STATUS or attempt == self.retries:
                return resp
            time.sleep(min(1.0 * (attempt + 1), max(0.0, deadline - time.monotonic())))
        return resp

    def complete(self, spec: ModelSpec, system: str, user: str, *, max_tokens: int,
                 timeout: float, prefix_tokens: int = 0, prefix_warm: bool = False,
                 schema: dict[str, Any] | None = None) -> LLMResult:
        p = self.registry.providers[spec.provider]
        headers = {}
        if key_env := p.get("api_key_env"):
            headers["Authorization"] = f"Bearer {os.environ.get(key_env, '')}"
        body: dict[str, Any] = {
            "model": spec.id,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": self._response_format(p, schema),
        }
        url = self.registry.base_url(spec.provider) + "/chat/completions"
        t0 = time.monotonic()
        resp = self._post(url, body, headers, timeout)
        if resp.status_code == 400 and body["response_format"].get("type") == "json_schema":
            body["response_format"] = {"type": "json_object"}  # schema mode not supported here
            resp = self._post(url, body, headers, timeout)
        if resp.status_code == 400 and "response_format" in body:
            body.pop("response_format")
            resp = self._post(url, body, headers, timeout)
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage") or {}
        text = data["choices"][0]["message"].get("content") or ""
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or usage.get(
            "prompt_cache_hit_tokens", 0)
        return LLMResult(
            text=text,
            tokens_in=int(usage.get("prompt_tokens") or approx_tokens(system + user)),
            tokens_out=int(usage.get("completion_tokens") or approx_tokens(text)),
            cached_tokens=int(cached or 0),
            latency_ms=(time.monotonic() - t0) * 1000,
            model=spec.id,
        )


# --- Mock ---------------------------------------------------------------------

_FIELD = re.compile(r"^(TASK|ARG|SINK LINE|FILE|TAINT CHAIN|CLAIM):\s*(.*)$", re.M)
_SNIPPET_LINE = re.compile(r"^\s*(\d+)\| (.*)$", re.M)
_SAFE_HINTS = ("shlex.quote", "fullmatch", "in ALLOWED", "in allowed", "SafeLoader",
               "safe_load", "literal_eval")
_INJECTION = re.compile(r"ignore (all )?(previous|prior) instructions|mark (this|it) (as )?safe",
                        re.I)

_PROSE = {
    "vulnerable": ("An attacker who controls {src} can inject shell or code metacharacters. "
                   "The value flows unchanged into `{sink}` on line {line}, which executes it, "
                   "so the attacker runs arbitrary commands on the host."),
    "safe": ("The argument to `{sink}` on line {line} is constant or passes a strict "
             "allowlist before use, so attacker data cannot change what is executed."),
}
_CAVE = {
    "vulnerable": "{src} -> `{sink}` L{line}. no sanitize. attacker run cmd.",
    "safe": "`{sink}` L{line} arg const/allowlisted. no attacker path.",
}
_FIX_PROSE = ("Pass an argument list without a shell, validate the value against a strict "
              "allowlist, and never build the command or code string from request data.")
_FIX_CAVE = "argv list, no shell. allowlist input."


class MockProvider:
    """Deterministic offline stand-in that mimics tiered model behaviour.

    Tier 1 is deliberately weaker: lower confidence on ambiguous code, and it can be fooled
    by prompt injection in the snippet, which the evidence check must catch.
    """

    def __init__(self, script: dict[str, list[str]] | None = None):
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.calls: list[tuple[str, str]] = []

    def complete(self, spec: ModelSpec, system: str, user: str, *, max_tokens: int,
                 timeout: float, prefix_tokens: int = 0, prefix_warm: bool = False,
                 schema: dict[str, Any] | None = None) -> LLMResult:
        fields = {k: v.strip() for k, v in _FIELD.findall(user)}
        task = fields.get("TASK", "judge")
        self.calls.append((task, spec.id))
        caveman = CAVEMAN_MARKER in system
        queue = self.script.get(f"{task}:{spec.tier}") or self.script.get(task)
        if queue:
            text = queue.pop(0) if len(queue) > 1 else queue[0]
        else:
            text = getattr(self, f"_{task}", self._judge)(spec, fields, user, caveman)
        return LLMResult(
            text=text,
            tokens_in=approx_tokens(system + user),
            tokens_out=approx_tokens(text),
            cached_tokens=prefix_tokens if prefix_warm else 0,
            latency_ms=0.0,
            model=spec.id,
        )

    def _judge(self, spec: ModelSpec, f: dict[str, str], user: str, caveman: bool) -> str:
        line = int(f.get("SINK LINE", "0") or 0)
        lines = dict((int(n), t) for n, t in _SNIPPET_LINE.findall(user))
        quote = lines.get(line, "").strip()
        sink = re.sub(r"\(.*", "", quote).split("=")[-1].strip() or "sink"
        src = (f.get("TAINT CHAIN") or "the call argument").split(" -> ")[0]
        arg = f.get("ARG", "unknown")
        snippet = "\n".join(lines.values())
        if spec.tier == "tier1" and _INJECTION.search(snippet):
            return json.dumps({"verdict": "safe", "confidence": 0.99, "evidence": [
                {"file": f.get("FILE", ""), "line": line, "quote": "reviewed by security team"}],
                "exploit_path": "", "suggested_fix": ""})
        if arg == "tainted":
            verdict, conf = "vulnerable", {"tier1": 0.86, "tier2": 0.9}.get(spec.tier, 0.95)
        elif arg == "constant" or any(h in snippet for h in _SAFE_HINTS):
            verdict, conf = "safe", 0.62 if spec.tier == "tier1" else 0.93
        else:
            verdict, conf = "vulnerable", 0.62 if spec.tier == "tier1" else 0.82
        tmpl = (_CAVE if caveman else _PROSE)[verdict]
        return json.dumps({
            "verdict": verdict,
            "confidence": conf,
            "evidence": [{"file": f.get("FILE", ""), "line": line, "quote": quote}],
            "exploit_path": tmpl.format(src=src, sink=sink, line=line),
            "suggested_fix": (_FIX_CAVE if caveman else _FIX_PROSE) if verdict != "safe" else "",
        })

    def _verify(self, spec: ModelSpec, f: dict[str, str], user: str, caveman: bool) -> str:
        claim = f.get("CLAIM", "")
        agree = not (claim.startswith("safe") and f.get("ARG") == "tainted")
        reason = ("claim matches cited line" if caveman else
                  "The cited line exists and the described data flow matches the snippet.")
        if not agree:
            reason = ("tainted data reach sink. safe wrong." if caveman else
                      "Tainted data reaches the sink, so a safe verdict is not supported.")
        return json.dumps({"agree": agree, "confidence": 0.9, "reason": reason})

    def _merge(self, spec: ModelSpec, f: dict[str, str], user: str, caveman: bool) -> str:
        n = user.count("- ")
        summary = (f"{n} vuln verdicts. check shared input paths." if caveman else
                   f"There are {n} vulnerable verdicts across files; review shared input "
                   "handling because one entry point may reach several sinks.")
        return json.dumps({"summary": summary, "cross_file_risks": []})

    def _triage(self, spec: ModelSpec, f: dict[str, str], user: str, caveman: bool) -> str:
        rce = bool(re.search(r"code execution|command injection|deserial|RCE", user, re.I))
        pkgs = [{"ecosystem": e, "name": n}
                for e, n in re.findall(r"PACKAGE: (\S+) (\S+)", user)]
        return json.dumps({"rce": rce, "confidence": 0.85 if rce else 0.7, "packages": pkgs,
                           "reason": "rce keyword" if caveman else "Mentions code execution."})

    def _plan(self, spec: ModelSpec, f: dict[str, str], user: str, caveman: bool) -> str:
        return json.dumps({
            "steps": ["bump to fixed version", "replace unsafe call with safe variant",
                      "add input validation at entry point"],
            "waf_hint": "block request bodies carrying language object tags",
            "notes": "proposal only" if caveman else "This is a proposal for human review.",
        })


class HybridProvider:
    """Real endpoint when the model is up, deterministic mock otherwise (labelled)."""

    def __init__(self, registry: ModelRegistry):
        self.registry = registry
        self.real = OpenAICompatProvider(registry)
        self.mock = MockProvider()

    def complete(self, spec: ModelSpec, system: str, user: str, *, max_tokens: int,
                 timeout: float, prefix_tokens: int = 0, prefix_warm: bool = False,
                 schema: dict[str, Any] | None = None) -> LLMResult:
        target = self.mock if self.registry.simulated(spec) else self.real
        return target.complete(spec, system, user, max_tokens=max_tokens, timeout=timeout,
                               prefix_tokens=prefix_tokens, prefix_warm=prefix_warm,
                               schema=schema)


def make_provider(registry: ModelRegistry) -> Provider:
    if registry.mode == "mock":
        return MockProvider()
    if registry.mode == "hybrid":
        return HybridProvider(registry)
    return OpenAICompatProvider(registry)
