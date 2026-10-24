"""Terminal and JSON rendering."""

from __future__ import annotations

import json
import re
import textwrap

from .models import Report, ScoredIssue

_CONTROL = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|[\x00-\x08\x0b-\x1f\x7f-\x9f]")
WIDTH = 100


def safe(text: str) -> str:
    """Strip terminal control sequences from untrusted text before printing."""
    return _CONTROL.sub("", text or "")


def _wrap(text: str, indent: str) -> str:
    return textwrap.fill(safe(text), width=WIDTH, initial_indent=indent, subsequent_indent=indent + "  ")


def _issue_block(pos: int, s: ScoredIssue) -> list[str]:
    i = s.issue
    lines = [f"{pos:>2}. [{s.score:>3}/100] {safe(i.display_id)}  {safe(i.title)[:90]}"]
    lines.append(f"      {safe(i.url)}")
    meta = []
    if i.labels:
        meta.append("labels: " + ", ".join(safe(lb) for lb in i.labels[:8]))
    if i.source != "github":
        meta.append(f"level: {i.level or '?'}  events: {i.event_count}  users: {i.user_count}")
    if i.assignees:
        meta.append("assigned: " + ", ".join(safe(a) for a in i.assignees[:3]))
    if i.comments:
        meta.append(f"comments: {i.comments}")
    if meta:
        lines.append("      " + " | ".join(meta))
    if not s.reasons:
        lines.append("      (no signals found; base score only)")
    for r in s.reasons:
        sign = "+" if r.points >= 0 else "-"
        lines.append(_wrap(f"{sign}{abs(r.points):>2} {r.signal}: {r.detail}", "      "))
    for f in s.flags:
        lines.append(_wrap(f"! {f}", "      "))
    return lines


def render_text(report: Report, *, top: int) -> str:
    out: list[str] = []
    src = {"github": "GitHub", "sentry": "Sentry", "glitchtip": "GlitchTip"}.get(report.source, report.source)
    out.append(f"Good First Issue Agent - {safe(report.target)} ({src})")
    out.append(safe(report.target_url))

    if report.ranked:
        shown = report.ranked[:top]
        summary = f"Fetched {report.fetched} open issue(s)"
        if report.source == "github":
            summary += f", excluded {report.excluded_pull_requests} pull request(s)"
        out.append(summary + f". Showing top {len(shown)}.")
        out.append("")
        for pos, s in enumerate(shown, 1):
            out.extend(_issue_block(pos, s))
            out.append("")
    elif report.selected is None:
        out.append("")
        out.append("No candidate issues found.")
        out.append("")

    sel = report.selected
    if sel:
        if not report.ranked:
            out.append("")
            out.extend(_issue_block(1, sel))
            out.append("")
        label = "selected issue" if not report.ranked else "top-ranked issue"
        out.append(f"Investigation plan for {safe(sel.issue.display_id)} ({label}, deterministic)")
        for n, step in enumerate(sel.next_steps, 1):
            out.append(_wrap(f"{n}. {step}", "  "))
        if sel.evidence_paths:
            where = "issue text" if sel.issue.source == "github" else "stack trace"
            out.append(_wrap("Files found in the " + where + ": " + ", ".join(sel.evidence_paths[:8]), "  "))
        if sel.uncertainties:
            out.append("  Open questions / uncertainty:")
            for u in sel.uncertainties:
                out.append(_wrap(f"- {u}", "    "))
        out.append("")

    if report.ai:
        out.append(f"AI analysis ({safe(report.ai.model)}) - model-generated recommendation, verify before acting")
        out.append("-" * 60)
        out.append(safe(report.ai.text).strip())
        out.append("-" * 60)
        for w in report.ai.warnings:
            out.append(_wrap(f"! {w}", "  "))
        out.append("")

    if report.warnings:
        out.append("Warnings:")
        for w in report.warnings:
            out.append(_wrap(f"- {w}", "  "))
        out.append("")

    out.append(
        "Note: scores are heuristics from labels and issue text, not a guarantee of difficulty. "
        "Nothing was changed on GitHub or the error tracker; this tool is read-only."
    )
    return "\n".join(out)


def render_json(report: Report, *, top: int) -> str:
    data = report.to_dict()
    data["ranked"] = data["ranked"][:top]
    return json.dumps(data, indent=2, ensure_ascii=False)
