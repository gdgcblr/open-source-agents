"""AI notes and risk warnings for human review.

AI never decides what is dead (see docs/adr/0001). For each removal it writes
a one-line note on what the code did and, where it sees one, a risk warning:
a reason the code may still be used in a way neither reading the code nor
running the tests can show. A risk warning makes the removal start out kept.

AI turns on automatically when an API key is found in the environment
(GEMINI_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY / OPENAI_BASE_URL),
and is off for a run with --no-ai. REAPER_AI_PROVIDER picks one explicitly.
Only standard-library HTTP is used, so no SDK is needed.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Callable

from .analyzer import ScanResult
from .model import Removal

BATCH_SIZE = 8
SNIPPET_LINES = 40

SYSTEM_PROMPT = """You help a developer review dead code before deleting it from a Python project.
Each item below was found unused by static analysis, and the project's checks still pass
without it. For each item, write:
- "note": one short sentence (max 15 words) saying what the code did, in plain language.
- "risk": null, or one short sentence if the code may still be used in a way neither static
  analysis nor tests can see: a framework hook or naming convention (pytest_* hooks, Django
  clean_<field>, signal handlers), a plugin or entry point loaded by name, public API that
  other projects import, or a call from a non-Python file, cron job, or deploy script.
Be decisive: clearly old, superseded, or orphaned code gets "risk": null.
Reply with a JSON array only, no prose and no code fences:
[{"number": 1, "note": "...", "risk": null}, ...]"""


class Provider:
    name = "provider"
    model = ""

    def complete(self, system: str, user: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    @staticmethod
    def _post(url: str, body: dict, headers: dict) -> dict:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers,
                                     method="POST")
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode())


class OpenAICompatible(Provider):
    """OpenAI's chat completions API shape. Also used for Gemini and Ollama."""

    def __init__(self, name: str, base_url: str, api_key: str, model: str):
        self.name, self.base_url, self.api_key, self.model = name, base_url.rstrip("/"), api_key, model

    def complete(self, system: str, user: str) -> str:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        data = self._post(f"{self.base_url}/chat/completions",
                          {"model": self.model, "temperature": 0,
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": user}]}, headers)
        return data["choices"][0]["message"]["content"]


class Anthropic(Provider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.anthropic.com"):
        self.api_key, self.model, self.base_url = api_key, model, base_url.rstrip("/")

    def complete(self, system: str, user: str) -> str:
        data = self._post(f"{self.base_url}/v1/messages",
                          {"model": self.model, "max_tokens": 2000, "system": system,
                           "messages": [{"role": "user", "content": user}]},
                          {"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                           "content-type": "application/json"})
        return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")


def detect_provider(env=None) -> Provider | None:
    """Pick a provider from the environment, or None if no key is set."""
    env = os.environ if env is None else env
    choice = (env.get("REAPER_AI_PROVIDER") or "").lower()
    model = env.get("REAPER_MODEL")
    if choice in ("", "gemini") and env.get("GEMINI_API_KEY"):
        return OpenAICompatible("gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
                                env["GEMINI_API_KEY"], model or "gemini-flash-latest")
    if choice in ("", "anthropic") and env.get("ANTHROPIC_API_KEY"):
        return Anthropic(env["ANTHROPIC_API_KEY"], model or "claude-haiku-5-5",
                         env.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"))
    if choice in ("", "openai") and (env.get("OPENAI_API_KEY") or env.get("OPENAI_BASE_URL")):
        return OpenAICompatible("openai", env.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                                env.get("OPENAI_API_KEY", ""), model or "gpt-5-mini")
    return None


def build_prompt(batch: list[Removal], scan: ScanResult) -> str:
    parts = []
    for r in batch:
        lines = scan.sources.get(r.path, "").splitlines()
        snippet = lines[r.start - 1:r.end][:SNIPPET_LINES]
        imports = [ln for ln in lines if ln.startswith(("import ", "from "))][:15]
        parts.append(
            f"### Item {r.number}: {r.kind} `{r.name}` in {r.path} (lines {r.start}-{r.end})\n"
            f"Detector notes: {'; '.join(r.reasons)}\n"
            f"File imports:\n" + ("\n".join(imports) or "(none)") + "\n"
            "Code:\n" + "\n".join(snippet))
    return "\n\n".join(parts)


def parse_response(text: str) -> dict[int, tuple[str | None, str | None]]:
    """Parse the model's JSON array into {number: (note, risk)}. Tolerates fences and prose."""
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return {}
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    out = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            number = int(item.get("number"))
        except (TypeError, ValueError):
            continue
        note = item.get("note")
        risk = item.get("risk")
        out[number] = (str(note)[:200] if note else None,
                       str(risk)[:300] if risk and str(risk).lower() != "null" else None)
    return out


def annotate(removals: list[Removal], scan: ScanResult, provider: Provider,
             log: Callable[[str], None] = print) -> int:
    """Add AI notes and risk warnings in place. Returns how many removals got a note."""
    noted = 0
    for i in range(0, len(removals), BATCH_SIZE):
        batch = removals[i:i + BATCH_SIZE]
        try:
            parsed = parse_response(provider.complete(SYSTEM_PROMPT, build_prompt(batch, scan)))
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError, OSError) as exc:
            log(f"  AI notes failed for {len(batch)} removals: {str(exc)[:160]}")
            continue
        for r in batch:
            if r.number in parsed:
                r.ai_note, r.risk = parsed[r.number]
                noted += 1
    return noted
