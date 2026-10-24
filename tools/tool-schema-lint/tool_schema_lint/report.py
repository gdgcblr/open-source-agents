"""Render lint results as human-readable text, JSON, or GitHub Actions annotations."""

from __future__ import annotations

import json

from . import __version__
from .linter import LintResult
from .models import Severity
from .rules import REGISTRY


def _summary(results: dict[str, LintResult]) -> dict[str, int]:
    findings = [f for r in results.values() for f in r.findings]
    return {
        "errors": sum(f.severity == Severity.ERROR for f in findings),
        "warnings": sum(f.severity == Severity.WARNING for f in findings),
        "info": sum(f.severity == Severity.INFO for f in findings),
    }


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def render_text(results: dict[str, LintResult]) -> str:
    lines: list[str] = []
    for path, result in results.items():
        lines.append(path)
        current_tool = None
        for f in result.findings:
            if f.tool != current_tool:
                current_tool = f.tool
                lines.append(f"  {f.tool if f.tool != '*' else '(all tools)'}")
            lines.append(f"    {f.severity!s:<8}{f.rule_id:<7}{f.path or '/'}")
            lines.append(f"            {f.message}")
            if f.hint:
                lines.append(f"            hint: {f.hint}")
        if not result.findings:
            lines.append("  no problems found")
        lines.append(
            f"  {_plural(result.tool_count, 'tool')}, ~{result.token_estimate} tokens (estimate), "
            f"targets: {', '.join(result.targets)}"
        )
        lines.append("")
    s = _summary(results)
    lines.append(f"{_plural(s['errors'], 'error')}, {_plural(s['warnings'], 'warning')}, {s['info']} info")
    return "\n".join(lines)


def render_json(results: dict[str, LintResult]) -> str:
    doc = {
        "tool": "tool-schema-lint",
        "version": __version__,
        "files": [
            {
                "file": path,
                "tool_count": r.tool_count,
                "token_estimate": r.token_estimate,
                "targets": r.targets,
                "findings": [f.to_dict() for f in r.findings],
            }
            for path, r in results.items()
        ],
        "summary": _summary(results),
    }
    return json.dumps(doc, indent=2, ensure_ascii=False)


def _gh_escape(text: str, prop: bool = False) -> str:
    text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if prop:
        text = text.replace(":", "%3A").replace(",", "%2C")
    return text


def render_github(results: dict[str, LintResult]) -> str:
    level = {Severity.ERROR: "error", Severity.WARNING: "warning", Severity.INFO: "notice"}
    lines = []
    for path, r in results.items():
        for f in r.findings:
            title = f"{f.rule_id} {f.tool}"
            body = f"{f.path or '/'}: {f.message}" + (f" ({f.hint})" if f.hint else "")
            lines.append(f"::{level[f.severity]} file={_gh_escape(path, True)},title={_gh_escape(title, True)}::"
                         f"{_gh_escape(body)}")
    s = _summary(results)
    lines.append(f"tool-schema-lint: {_plural(s['errors'], 'error')}, {_plural(s['warnings'], 'warning')}, "
                 f"{s['info']} info")
    return "\n".join(lines)


def render_rules() -> str:
    lines = [f"{'ID':<7}{'SEVERITY':<9}{'TARGETS':<26}SUMMARY"]
    for r in sorted(REGISTRY.values(), key=lambda r: r.id):
        targets = ",".join(sorted(r.targets)) if r.targets else "all"
        lines.append(f"{r.id:<7}{r.severity!s:<9}{targets:<26}{r.summary}")
        lines.append(f"{'':<16}source: {r.source}")
    return "\n".join(lines)


RENDERERS = {"text": render_text, "json": render_json, "github": render_github}
