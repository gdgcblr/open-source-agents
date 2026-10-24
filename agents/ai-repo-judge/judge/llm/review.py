"""LLM review: build a compact, injection-hardened context for one submission and parse a
schema-validated verdict. The LLM never sets the final score; scoring.py blends its 1-5 ratings
with the static checks under a fixed cap."""

from __future__ import annotations

import json
import logging
import re
from importlib import resources
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from judge.llm.client import ChatClient, LLMError
from judge.models import SEVERITY_RANK, AnalyzerResult, Claim
from judge.workspace import Workspace

log = logging.getLogger(__name__)

PROMPT_VERSION = "review_v2"
SCORE_KEYS = (
    "code_structure",
    "functionality",
    "security_posture",
    "ai_depth",
    "prompt_quality",
    "ai_guardrails",
    "docs_clarity",
    "example_realism",
    "novelty",
    "usefulness",
)
BUDGET = {"readme": 4500, "tree": 1200, "static": 1600, "code": 7000}
TAG = "untrusted_submission"


def _clamp(v: Any) -> int:
    try:
        return max(1, min(5, round(float(v))))
    except (TypeError, ValueError):
        return 3


class LLMRisk(BaseModel):
    title: str
    detail: str = ""
    file: str | None = None
    line: int | None = None
    severity: str = "low"

    @field_validator("severity", mode="before")
    @classmethod
    def _sev(cls, v: Any) -> str:
        v = str(v).lower()
        return v if v in ("low", "medium", "high") else "low"  # the LLM cannot raise critical/gating findings

    @field_validator("line", mode="before")
    @classmethod
    def _line(cls, v: Any) -> int | None:
        try:
            return int(v) if v else None
        except (TypeError, ValueError):
            return None


class LLMReview(BaseModel):
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    top_fixes: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    scores: dict[str, int] = Field(default_factory=dict)
    rationales: dict[str, str] = Field(default_factory=dict)
    risks: list[LLMRisk] = Field(default_factory=list)
    manipulation_attempt: bool = False
    manipulation_evidence: str = ""
    provider: str | None = None
    model: str | None = None
    tokens: int = 0
    prompt_version: str = PROMPT_VERSION

    @field_validator("scores", mode="before")
    @classmethod
    def _scores(cls, v: Any) -> dict[str, int]:
        v = v if isinstance(v, dict) else {}
        return {k: _clamp(v.get(k)) for k in SCORE_KEYS}

    @field_validator("claims", mode="before")
    @classmethod
    def _claims(cls, v: Any) -> list:
        out = []
        for c in v if isinstance(v, list) else []:
            if isinstance(c, dict) and c.get("feature"):
                status = str(c.get("status", "partial")).lower()
                out.append(
                    {
                        "feature": str(c["feature"])[:120],
                        "evidence": str(c.get("evidence", ""))[:200],
                        "status": status
                        if status in ("implemented", "partial", "missing", "unverified")
                        else "unverified",
                    }
                )
        return out[:6]

    @field_validator("strengths", "top_fixes", mode="before")
    @classmethod
    def _short_list(cls, v: Any) -> list[str]:
        return [str(x)[:240] for x in (v if isinstance(v, list) else [])][:3]


def _neutralise(text: str) -> str:
    """Stop submitted text from closing our data delimiter."""
    return re.sub(TAG, TAG.replace("_", "-"), text, flags=re.I)


def _numbered(text: str, start: int, end: int) -> str:
    lines = text.splitlines()
    return "\n".join(f"{i:>4}| {lines[i - 1]}" for i in range(start, min(end, len(lines)) + 1))


def code_excerpts(ws: Workspace, sites: list[str], budget: int) -> str:
    """Line-numbered windows around LLM call sites, then the entry point, then the largest sources."""
    windows: dict[str, list[tuple[int, int]]] = {}
    for site in sites:
        rel, _, line = site.rpartition(":")
        if line.isdigit():
            windows.setdefault(rel, []).append((max(1, int(line) - 20), int(line) + 25))
    entry = next(
        (
            f
            for f in (
                "main.py",
                "app.py",
                "agent.py",
                "server.py",
                "cli.py",
                "index.ts",
                "index.js",
                "src/index.ts",
                "src/main.py",
            )
            if ws.exists(f)
        ),
        None,
    )
    order = list(windows)
    if entry and entry not in windows:
        windows[entry] = [(1, 70)]
        order.append(entry)
    for rel in sorted(ws.source_files, key=ws.line_count, reverse=True):
        if rel not in windows:
            windows[rel] = [(1, 50)]
            order.append(rel)
    out, used = [], 0
    for rel in order:
        text = ws.read(rel)
        if not text:
            continue
        spans = sorted(windows[rel])
        merged: list[list[int]] = []
        for a, b in spans:
            if merged and a <= merged[-1][1] + 5:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        for a, b in merged:
            chunk = f"### {rel} (lines {a}-{b})\n{_numbered(text, a, b)}\n"
            if used + len(chunk) > budget:
                remaining = budget - used
                if remaining > 400:
                    out.append(chunk[:remaining] + "\n…(truncated)\n")
                return "\n".join(out)
            out.append(chunk)
            used += len(chunk)
    return "\n".join(out)


def build_context(ws: Workspace, results: dict[str, AnalyzerResult]) -> str:
    facts = {k: v.facts for k, v in results.items()}
    ai = facts.get("ai_native", {})
    tree = "\n".join(f"{f} ({ws.line_count(f)} lines)" for f in ws.files[:80])[: BUDGET["tree"]]
    issues = [
        f"- [{c.status}] {c.label}: {c.detail}"
        for r in results.values()
        for c in r.checks
        if c.status in ("warn", "fail")
    ]
    top = sorted((f for r in results.values() for f in r.findings), key=lambda f: -SEVERITY_RANK[f.severity])[:12]
    issues += [f"- {f.severity}: {f.title} ({f.file}:{f.line})" for f in top]
    readme = re.sub(r"!\[[^\]]*\]\([^)]*\)|<img[^>]*>", "", ws.readme)
    readme = re.sub(r"\n{3,}", "\n\n", readme)[: BUDGET["readme"]]
    header = {
        "project_path": ws.project_path,
        "category": ws.category,
        "languages": sorted({ws.language(f) for f in ws.code_files}),
        "providers_detected": ai.get("providers", []),
        "frameworks_detected": ai.get("frameworks", []),
        "ai_level_static": f"{ai.get('ai_level', 0)} ({ai.get('ai_level_label', '')})",
    }
    body = (
        f"## Static analysis summary\n{json.dumps(header)}\n"
        + "\n".join(issues)[: BUDGET["static"]]
        + f"\n\n## File tree\n{tree}\n\n## README.md\n{readme}\n\n## Code excerpts\n"
        f"{code_excerpts(ws, ai.get('llm_sites', []), BUDGET['code'])}"
    )
    return f"<{TAG}>\n{_neutralise(body)}\n</{TAG}>\n\nReturn the JSON review now."


def system_prompt() -> str:
    return resources.files("judge.llm.prompts").joinpath(f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")


def review(ws: Workspace, results: dict[str, AnalyzerResult], client: ChatClient) -> LLMReview:
    context = build_context(ws, results)
    res = client.chat_json(system_prompt(), context, max_tokens=1800)
    try:
        data = json.loads(_extract_json(res.text))
        parsed = LLMReview.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise LLMError(f"invalid review JSON from {res.provider}: {exc}") from exc
    parsed.provider, parsed.model, parsed.tokens = res.provider, res.model, res.tokens
    return parsed


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start >= 0 and end > start else text


def mock_review(ws: Workspace, results: dict[str, AnalyzerResult]) -> LLMReview:
    """Deterministic stand-in so the pipeline and dashboard work without any API key.

    Ratings mirror the static scores, and claims come from README bullet points matched against code."""

    def static(dim: str) -> int:
        checks = [c for c in results[dim].checks if c.status != "skip"]
        if not checks:
            return 3
        val = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
        s = sum(c.weight * (c.score if c.score is not None else val[c.status]) for c in checks)
        return _clamp(1 + 4 * s / sum(c.weight for c in checks))

    code = " ".join((ws.read(f) or "").lower() for f in ws.source_files)
    claims = []
    for line in re.findall(r"^\s*[-*]\s+\**([^*\n:]{6,80})", ws.readme, re.M)[:6]:
        words = [w for w in re.findall(r"[a-z]{5,}", line.lower())][:4]
        hits = sum(w[:6] in code for w in words)
        status = "implemented" if words and hits >= len(words) / 2 else "partial" if hits else "missing"
        claims.append({"feature": line.strip(), "status": status, "evidence": "keyword match (mock reviewer)"})
    q, d, a, f, s = (static(k) for k in ("quality", "docs", "ai_native", "functionality", "security"))
    return LLMReview.model_validate(
        {
            "summary": f"Mock review of {ws.slug}. Ratings mirror the static analysis; run with an LLM for real judgement.",
            "strengths": [],
            "top_fixes": [],
            "claims": claims,
            "scores": {
                "code_structure": q,
                "functionality": f,
                "security_posture": s,
                "ai_depth": a,
                "prompt_quality": a,
                "ai_guardrails": a,
                "docs_clarity": d,
                "example_realism": d,
                "novelty": 3,
                "usefulness": 3,
            },
            "rationales": {k: "mock reviewer" for k in SCORE_KEYS},
            "provider": "mock",
            "model": "mock",
        }
    )
