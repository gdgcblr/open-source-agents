"""Render findings as text or JSON and compute the exit code."""

import json

from .rules import SEVERITIES

LABELS = {"high": "HIGH", "medium": "MED ", "low": "LOW "}


def sort_findings(findings):
    return sorted(findings, key=lambda f: (-SEVERITIES.index(f.severity), f.server, f.tool, f.rule_id))


def summarize(findings):
    return {severity: sum(f.severity == severity for f in findings) for severity in reversed(SEVERITIES)}


def render_text(findings, scanned, notes=()):
    lines = []
    for server, count in scanned.items():
        lines.append(f"Scanned {count} tool(s) from {server}")
    lines += list(notes)
    if not scanned:
        return "\n".join(lines)
    if not findings:
        lines.append("No findings.")
        return "\n".join(lines)
    lines.append("")
    for f in sort_findings(findings):
        where = f"{f.server}/{f.tool}" if f.server else f.tool
        if f.path:
            where += f" [{f.path}]"
        lines.append(f"{LABELS[f.severity]} {f.rule_id:<22} {where}")
        lines.append(f"     {f.message}")
        if f.evidence:
            lines.append(f"     evidence: {f.evidence}")
    counts = summarize(findings)
    lines.append("")
    lines.append(f"{len(findings)} finding(s): " + ", ".join(f"{n} {s}" for s, n in counts.items()))
    return "\n".join(lines)


def render_json(findings, scanned, notes=()):
    return json.dumps({
        "scanned": scanned,
        "notes": list(notes),
        "summary": summarize(findings),
        "findings": [f.to_dict() for f in sort_findings(findings)],
    }, indent=2, ensure_ascii=True)


def exit_code(findings, fail_on):
    threshold = SEVERITIES.index(fail_on)
    return 1 if any(SEVERITIES.index(f.severity) >= threshold for f in findings) else 0
