"""Guardrails: deterministic checks around every model boundary.

    evidence in  ─▶ [redact secrets/PII] ─▶ [quarantine prompt injection] ─▶ model
    tool calls   ─▶ [per-agent tool budget]
    report out   ─▶ [fix-command policy] ─▶ [evidence grounding] ─▶ [verdict invariants] ─▶ human

Nothing here calls an LLM, so the checks cannot be argued with by the content they inspect.
"""

from __future__ import annotations

import json
import re
from typing import Any

from google.adk.tools import BaseTool, ToolContext

from .schema import RCAReport

# --- input guardrails: redaction -------------------------------------------

REDACTIONS: list[tuple[str, re.Pattern]] = [
    # END is optional: a diff truncated mid-key must still be redacted.
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}")),
    ("db_url_password", re.compile(r"(?<=://)[^:/\s@]+:[^@\s/]+(?=@)")),
    ("secret_assignment", re.compile(r"(?i)\b(password|passwd|secret|api_key|token)\s*[=:]\s*[^\s,;\"']{4,}")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]

# --- input guardrails: prompt injection -------------------------------------

INJECTION_PATTERNS = [
    re.compile(p, re.I) for p in (
        r"ignore (?:all |any )?(?:previous|prior|above|earlier) (?:instructions|findings|rules)",
        r"disregard (?:all |the )?(?:previous|prior|above|system)",
        r"\byou are now\b",
        r"\b(?:system|assistant)\s*(?:prompt|message)?\s*:",
        r"\bnew instructions?\b",
        r"\broot cause is\b",
        r"\bimmediate_fix\b",
        r"(?:curl|wget)\s+[^|]*\|\s*(?:ba|z)?sh",
    )
]

QUARANTINE = "[QUARANTINED by guardrail: text in evidence looked like instructions to the AI]"

TOOL_BUDGET = {"triage": 4, "skeptic": 10}
DEFAULT_TOOL_BUDGET = 8


def _empty() -> dict:
    return {"redactions": {}, "injections": [], "budget_hits": []}


def _events(state, agent: str) -> dict:
    # One key per agent: parallel investigators never read-modify-write the same state entry.
    return dict(state.get(f"guardrails:{agent}", _empty()))


def merged_events(state: dict) -> dict:
    out = _empty()
    for key, ev in state.items():
        if key.startswith("guardrails:"):
            for k, n in ev["redactions"].items():
                out["redactions"][k] = out["redactions"].get(k, 0) + n
            out["injections"] += ev["injections"]
            out["budget_hits"] += ev["budget_hits"]
    return out


def evidence_corpus(state: dict) -> str:
    return "\n".join(v for k, v in state.items() if k.startswith("evidence:"))


def redact_text(text: str, counts: dict[str, int]) -> str:
    for name, pattern in REDACTIONS:
        text, n = pattern.subn(f"[REDACTED:{name}]", text)
        if n:
            counts[name] = counts.get(name, 0) + n
    return text


def find_injection(text: str) -> str | None:
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            return pattern.pattern
    return None


def _clean(value: Any, counts: dict[str, int], hits: list[dict], tool: str) -> Any:
    if isinstance(value, str):
        value = redact_text(value, counts)
        # Quarantine line by line: an attacker who plants instructions in the culprit commit
        # must not be able to hide the rest of that diff from the investigators.
        lines = value.split("\n")
        for i, line in enumerate(lines):
            rule = find_injection(line)
            if rule:
                hits.append({"tool": tool, "rule": rule, "excerpt": line[:160]})
                lines[i] = QUARANTINE
        return "\n".join(lines)
    if isinstance(value, list):
        return [_clean(v, counts, hits, tool) for v in value]
    if isinstance(value, dict):
        return {k: _clean(v, counts, hits, tool) for k, v in value.items()}
    return value


def sanitize_text(text: str, source: str = "external") -> dict:
    """Input guardrail on arbitrary text (used by the MCP server)."""
    counts: dict[str, int] = {}
    hits: list[dict] = []
    return {"text": _clean(text, counts, hits, source), "redactions": counts, "injections": hits}


def sanitize_tool_output(tool: BaseTool, args: dict, tool_context: ToolContext, tool_response: Any) -> dict:
    """ADK after_tool_callback: redact and quarantine every tool result before the model sees it."""
    agent = tool_context.agent_name
    events = _events(tool_context.state, agent)
    counts = dict(events["redactions"])
    hits: list[dict] = []
    cleaned = _clean(tool_response, counts, hits, tool.name)
    events["redactions"] = counts
    events["injections"] = events["injections"] + hits
    tool_context.state[f"guardrails:{agent}"] = events
    # Keep what the model actually saw, so the report can be grounded against it.
    key = f"evidence:{agent}"
    tool_context.state[key] = tool_context.state.get(key, "") + "\n" + json.dumps(cleaned, default=str)
    return cleaned if isinstance(cleaned, dict) else {"result": cleaned}


def enforce_tool_budget(tool: BaseTool, args: dict, tool_context: ToolContext) -> dict | None:
    """ADK before_tool_callback: cap tool calls per agent so a confused or hijacked agent can't loop on paid work."""
    agent = tool_context.agent_name
    key = f"tool_calls:{agent}"
    used = tool_context.state.get(key, 0) + 1
    tool_context.state[key] = used
    limit = TOOL_BUDGET.get(agent, DEFAULT_TOOL_BUDGET)
    if used > limit:
        events = _events(tool_context.state, agent)
        events["budget_hits"] = events["budget_hits"] + [{"agent": agent, "tool": tool.name, "limit": limit}]
        tool_context.state[f"guardrails:{agent}"] = events
        return {"error": f"Tool budget of {limit} calls reached. Conclude from the evidence you already have."}
    return None


# --- output guardrails -------------------------------------------------------

_SAFE = r"[A-Za-z0-9._\-]+"
ALLOWED_FIXES = [
    ("git revert", re.compile(rf"^git revert (?:--no-edit )?[0-9a-f]{{7,40}}$")),
    ("traffic rollback", re.compile(rf"^gcloud run services update-traffic {_SAFE} --to-revisions[= ]{_SAFE}=100(?: --region[= ]{_SAFE})?$")),
    ("env var change", re.compile(rf"^gcloud run services update {_SAFE} --(?:update|set)-env-vars[= ]{_SAFE}={_SAFE}(?: --region[= ]{_SAFE})?$")),
    ("dependency pin", re.compile(rf"^(?:pip install|uv add) {_SAFE}(?:==|<){_SAFE}$")),
]
_SHELL_META = re.compile(r"[;&|`$<>(){}\\\n]")


def check_fix(command: str) -> tuple[bool, str]:
    cmd = command.strip()
    if _SHELL_META.search(cmd):
        return False, "contains shell metacharacters"
    for name, pattern in ALLOWED_FIXES:
        if pattern.match(cmd):
            return True, f"matches allowlisted pattern: {name}"
    return False, "not an allowlisted remediation (git revert, Cloud Run traffic rollback, env var change, dependency pin)"


def safe_rollback(incident: dict, culprit: str) -> str:
    """Fallback fix built from data, not model text: route traffic to the last revision before the culprit."""
    deploys = sorted(incident["deploys"], key=lambda d: d["deployed_at"])
    service = incident["alert"]["service"]
    for i, d in enumerate(deploys):
        if d["sha"] == culprit or culprit in incident["diffs"].get(d["sha"], ""):
            if i > 0:
                return f"gcloud run services update-traffic {service} --to-revisions={deploys[i - 1]['revision']}=100"
            break
    return "Manual review required: no known-good revision to roll back to"


_KEY_TOKEN = re.compile(r"\b[0-9a-f]{7,40}\b|\b[A-Z][A-Z0-9_]{3,}\b|\b\d[\d,]*(?:\.\d+)?\b")


def grounding(report: RCAReport, corpus: str) -> dict:
    """Fraction of concrete tokens (shas, numbers, CONSTANTS) in each evidence line that appear in tool output."""
    corpus_l = corpus.lower()
    ungrounded, checked, grounded = [], 0, 0
    for cause in report.causes:
        for ev in cause.evidence:
            tokens = {t.replace(",", "") for t in _KEY_TOKEN.findall(ev)}
            tokens = {t for t in tokens if len(t) > 1}
            if not tokens:
                continue
            checked += 1
            found = sum(1 for t in tokens if t.lower() in corpus_l or t.lower() in corpus_l.replace(",", ""))
            if found / len(tokens) >= 0.5:
                grounded += 1
            else:
                ungrounded.append(ev)
    culprit_ok = report.culprit.lower() in corpus_l
    return {
        "score": round(grounded / checked, 2) if checked else 1.0,
        "checked": checked,
        "ungrounded": ungrounded[:5],
        "culprit_in_evidence": culprit_ok,
    }


def review_report(report: RCAReport, incident: dict, state: dict) -> tuple[RCAReport, dict]:
    """Apply output guardrails. Returns the (possibly corrected) report and a guardrail summary."""
    events = merged_events(state)
    checks: list[dict] = []

    ok, reason = check_fix(report.immediate_fix)
    fix = {"original": report.immediate_fix, "allowed": ok, "reason": reason}
    if not ok:
        report = report.model_copy(update={"immediate_fix": safe_rollback(incident, report.culprit)})
        fix["replacement"] = report.immediate_fix
    checks.append({"name": "Remediation allowlist", "passed": ok, "detail": reason})

    roots = [c for c in report.causes if c.verdict == "root_cause"]
    single = len(roots) == 1
    checks.append({"name": "Exactly one root cause", "passed": single, "detail": f"{len(roots)} root cause(s)"})

    g = grounding(report, evidence_corpus(state))
    checks.append({"name": "Evidence grounded in tool output", "passed": g["score"] >= 0.7,
                   "detail": f"{int(g['score'] * 100)}% of {g['checked']} evidence lines traced to tool output"})
    checks.append({"name": "Culprit seen in evidence", "passed": g["culprit_in_evidence"], "detail": report.culprit})

    conf = roots[0].confidence if roots else 0.0
    checks.append({"name": "Root-cause confidence ≥ 0.6", "passed": conf >= 0.6, "detail": f"{conf:.2f}"})

    inj = events["injections"]
    checks.append({"name": "No prompt injection reached the model", "passed": True,
                   "detail": f"{len(inj)} injection attempt(s) quarantined" if inj else "none detected"})

    blocking = [c for c in checks if not c["passed"] and c["name"] != "Remediation allowlist"]
    decision = "needs_human_review" if blocking or inj else "ready_for_approval"
    summary = {
        "decision": decision,
        "checks": checks,
        "fix_policy": fix,
        "grounding": g,
        "redactions": events["redactions"],
        "injections": inj,
        "budget_hits": events["budget_hits"],
    }
    return report, summary
