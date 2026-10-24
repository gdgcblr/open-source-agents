"""Output adapter: Markdown report. The whole document is redacted before it is returned."""
from collections import Counter

from ..models import Category, TriageResult
from ..privacy import redact

ICON = {Category.FLAKY: "🎲", Category.INFRA: "🏗️", Category.REGRESSION: "🐛", Category.UNKNOWN: "❓"}


def render(result: TriageResult, provider_name: str) -> str:
    counts = Counter(r.verdict.category for r in result.results)
    lines = ["# CI Failure Triage Report", "",
             f"**{len(result.results)} failing test(s)** out of {result.total_tests} • provider: `{provider_name}`", "",
             "| Category | Count |", "|---|---|"]
    lines += [f"| {ICON[c]} {c.value} | {counts.get(c, 0)} |" for c in Category]
    lines.append("")
    for r in result.results:
        v, f = r.verdict, r.failure
        lines += [f"## {ICON[v.category]} {f.classname + '.' if f.classname else ''}{f.name}",
                  f"- **Verdict:** {v.category.value} (confidence {v.confidence:.2f}, source: {v.source})",
                  "- **Evidence:**", *[f"  - {e}" for e in v.evidence],
                  f"- **Suggested action:** {v.suggested_action}"]
        if r.note:
            lines.append(f"- **Note:** {r.note}")
        lines.append("")
    body = redact("\n".join(lines))  # redact first, then append the audit line (counts only, no values)
    if result.pii_counts:
        kinds = ", ".join(f"{k.lower().replace('_', ' ')} x{n}" for k, n in sorted(result.pii_counts.items()))
        audit = f"🔒 **Privacy:** replaced before analysis and in this report: {kinds}. Values are never stored or sent."
    else:
        audit = "🔒 **Privacy:** no secrets or PII found by the built-in detectors (names and free text cannot be detected by pattern)."
    return f"{body}\n{audit}\n\n_Triage is heuristic. Treat verdicts as a starting point, not a final judgement._"
