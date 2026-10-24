"""Render a ReviewResult as Markdown (for PR comments) or JSON (for CI)."""
from __future__ import annotations

import json

from .models import SEVERITIES, ReviewResult
from .guardrails import redact

ICON = {"critical": "🚨", "high": "🔴", "medium": "🟠", "low": "🟡", "info": "🔵"}
VERDICT_LABEL = {
    "APPROVE": "✅ Looks good",
    "COMMENT": "💬 Minor issues",
    "REQUEST_CHANGES": "❌ Changes requested",
}


def to_markdown(r: ReviewResult) -> str:
    counts = r.counts()
    badge = " · ".join(f"{ICON[s]} {counts[s]} {s}" for s in SEVERITIES if counts[s])
    out = [
        "## 🤖 AI PR Review",
        f"**Verdict:** {VERDICT_LABEL[r.verdict]}  ",
        f"**Findings:** {badge or 'none 🎉'}",
        "",
        r.summary,
        "",
    ]
    for f in r.findings:
        out.append(f"### {ICON[f.severity]} {f.title}")
        out.append(f"`{f.file}:{f.line}` · {f.severity} · {f.category} · _{f.source}_")
        out.append("")
        out.append(f.detail)
        if f.suggestion:
            out.append(f"\n**Suggestion:** {f.suggestion}")
        out.append("")
    if r.notes:
        out.append("<details><summary>Review notes</summary>\n")
        out.extend(f"- {n}" for n in r.notes)
        out.append("\n</details>")
    s = r.stats
    out.append(
        f"\n<sub>{s.get('files_changed', 0)} files · +{s.get('lines_added', 0)} lines · "
        f"provider: {s.get('provider')}</sub>"
    )
    return redact("\n".join(out))


def to_json(r: ReviewResult) -> str:
    return redact(json.dumps(r.to_dict(), indent=2))
