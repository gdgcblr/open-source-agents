"""Reporting. Only ever formats redacted data."""

from __future__ import annotations

import json

from .guardrails import mask_obj, mask_text
from .models import SEVERITIES, Finding
from .remediation import COMMON_STEPS
from .scanner import ScanResult


def _sort_key(f: Finding):
    return (-SEVERITIES.index(f.severity), f.candidate.file, f.candidate.line)


def to_dict(result: ScanResult) -> dict:
    rep = sorted(result.reportable, key=_sort_key)
    dismissed = [f for f in result.findings if not f.reportable]
    return {
        "summary": {
            "reportable": len(rep),
            "dismissed": len(dismissed),
            "by_severity": {s: sum(1 for f in rep if f.severity == s) for s in reversed(SEVERITIES)},
            **result.stats,
        },
        "warnings": list(result.warnings),
        "exit_code": result.exit_code,
        "findings": [f.to_dict() for f in rep],
        "dismissed": [f.to_dict() for f in sorted(dismissed, key=_sort_key)],
    }


def to_json(result: ScanResult) -> str:
    return json.dumps(mask_obj(to_dict(result)), indent=2)


def to_markdown(result: ScanResult, show_dismissed: bool = True) -> str:
    d = to_dict(result)
    s = d["summary"]
    out = ["# Secret scan report", ""]
    mode = s.get("mode", "?")
    out.append(f"- Mode: `{mode}`" + (f" (model `{s['model']}`)" if s.get("model") else
                                       " (no LLM triage: every deterministic match is reported as unverified)"))
    out.append(f"- Files scanned: {s.get('files_scanned', 0)}; candidates: {s.get('candidates', 0)}; "
               f"reported: {s['reportable']}; dismissed by triage: {s['dismissed']}")
    skipped = {k: v for k, v in s.items() if k.startswith("skipped_") and v}
    if skipped:
        out.append("- Skipped: " + ", ".join(f"{k[8:]}={v}" for k, v in skipped.items()))
    for w in d["warnings"]:
        out.append(f"- **WARNING**: {w}")
    out.append("")
    if not d["findings"]:
        out.append("No findings reported." + (" (scan incomplete: see warnings)" if result.incomplete else ""))
    for f in d["findings"]:
        out += [
            f"## [{f['severity'].upper()}] `{f['file']}:{f['line']}` - {f['kind']}",
            "",
            f"- Rule: `{f['rule']}`; value: `{f['redacted_value']}`",
            f"- Verdict: **{f['verdict']}** (confidence {f['confidence']:.2f}, decided by {f['decided_by']})",
            f"- Why: {f['reason']}",
        ]
        if f["llm_note"]:
            out.append(f"- Note: {f['llm_note']}")
        out += [f"- Fix: {f['remediation']}", "", "```"] + f["context"] + ["```", ""]
    if d["findings"]:
        out += ["## Remediation checklist", ""]
        out += [f"{i}. {step}" for i, step in enumerate(COMMON_STEPS, 1)]
        out.append("")
    if show_dismissed and d["dismissed"]:
        out += ["## Dismissed by LLM triage", ""]
        for f in d["dismissed"]:
            out.append(f"- `{f['file']}:{f['line']}` {f['rule']} -> {f['verdict']} "
                       f"({f['confidence']:.2f}): {f['reason']}")
        out.append("")
    return mask_text("\n".join(out))
