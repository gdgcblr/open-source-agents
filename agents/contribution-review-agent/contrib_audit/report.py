"""Report renderers: text, markdown, and JSON."""
from __future__ import annotations

import json
from pathlib import Path

from .models import AuditResult, Severity, Verdict

# ANSI colour codes (disabled on Windows when not supported)
_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_MAGENTA = "\033[35m"

_VERDICT_COLOUR = {
    Verdict.READY: _GREEN,
    Verdict.APPROVE_WITH_NITS: _CYAN,
    Verdict.CHANGES_REQUESTED: _YELLOW,
    Verdict.REJECT: _RED,
}

_SEVERITY_COLOUR = {
    Severity.ERROR: _RED,
    Severity.WARNING: _YELLOW,
    Severity.INFO: _CYAN,
}

_SEVERITY_ICON = {
    Severity.ERROR: "✗",
    Severity.WARNING: "⚠",
    Severity.INFO: "ℹ",
}


def _colour(text: str, code: str, use_colour: bool) -> str:
    if not use_colour:
        return text
    return f"{code}{text}{_RESET}"


def render_text(result: AuditResult, use_colour: bool = True) -> str:
    lines: list[str] = []
    v = result.verdict

    lines.append("")
    lines.append(
        _colour(f"  Contribution Review — {result.project_name}", _BOLD, use_colour)
    )
    lines.append(f"  Path: {result.project_path}")
    lines.append("")
    verdict_str = f"  Verdict: {v.value}"
    lines.append(_colour(verdict_str, _VERDICT_COLOUR.get(v, ""), use_colour))
    lines.append("")

    if not result.findings:
        lines.append(_colour("  No findings — all checks passed!", _GREEN, use_colour))
    else:
        lines.append(f"  Findings ({len(result.findings)} total):")
        for f in result.findings:
            sev_icon = _SEVERITY_ICON.get(f.severity, "?")
            sev_col = _SEVERITY_COLOUR.get(f.severity, "")
            loc = ""
            if f.file:
                loc = f"  {f.file}"
                if f.line:
                    loc += f":{f.line}"
            prefix = _colour(f"  [{sev_icon}] [{f.rule_id}]", sev_col, use_colour)
            lines.append(f"{prefix} {f.message}")
            if loc:
                lines.append(f"       {loc}")
            if f.evidence:
                lines.append(f"       Evidence: {f.evidence}")
            lines.append(f"       Fix: {f.fix_hint}")
            lines.append("")

    lines.append("")
    return "\n".join(lines)


def render_markdown(result: AuditResult) -> str:
    v = result.verdict
    lines: list[str] = []

    verdict_badge = {
        Verdict.READY: "🟢 READY",
        Verdict.APPROVE_WITH_NITS: "🔵 APPROVE WITH NITS",
        Verdict.CHANGES_REQUESTED: "🟡 CHANGES REQUESTED",
        Verdict.REJECT: "🔴 REJECT",
    }

    lines.append(f"# Contribution Review: `{result.project_name}`")
    lines.append("")
    lines.append(f"**Path:** `{result.project_path}`")
    lines.append("")
    lines.append(f"## Verdict: {verdict_badge.get(v, v.value)}")
    lines.append("")

    if not result.findings:
        lines.append("✅ No findings — all checks passed!")
    else:
        # Group by severity
        for sev, icon, heading in [
            (Severity.ERROR, "❌", "Errors (must fix)"),
            (Severity.WARNING, "⚠️", "Warnings (should fix)"),
            (Severity.INFO, "ℹ️", "Info (informational)"),
        ]:
            group = [f for f in result.findings if f.severity == sev]
            if not group:
                continue
            lines.append(f"### {icon} {heading}")
            lines.append("")
            lines.append("| Rule | File | Line | Message | Fix |")
            lines.append("|------|------|------|---------|-----|")
            for f in group:
                file_str = str(f.file) if f.file else ""
                line_str = str(f.line) if f.line else ""
                msg = f.message.replace("|", "\\|")
                fix = f.fix_hint.replace("|", "\\|")
                lines.append(f"| {f.rule_id} | `{file_str}` | {line_str} | {msg} | {fix} |")
            lines.append("")

    return "\n".join(lines)


def render_json(result: AuditResult) -> str:
    return json.dumps(result.to_dict(), indent=2)
