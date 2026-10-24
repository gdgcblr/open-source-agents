"""Markdown and JSON report rendering."""

from __future__ import annotations

import json
from dataclasses import asdict
from urllib.parse import quote

from first_pr_compass.analyzer import Analysis, Finding


def _evidence_link(
    finding: Finding, source_url: str | None = None, source_ref: str | None = None
) -> str:
    evidence = finding.evidence
    relative_path = quote(evidence.path, safe="/._-")
    if source_url and source_ref:
        target = (
            f"{source_url}/blob/{quote(source_ref, safe='/._-')}/"
            f"{relative_path}#L{evidence.line}"
        )
    else:
        target = relative_path + f"#L{evidence.line}"
    label = evidence.path.replace("[", r"\[").replace("]", r"\]")
    return f"[{label}:{evidence.line}]({target})"


def _render_section(
    title: str,
    findings: list[Finding],
    empty_message: str,
    source_url: str | None = None,
    source_ref: str | None = None,
) -> list[str]:
    output = [f"## {title}", ""]
    if not findings:
        output.extend([empty_message, ""])
        return output

    for finding in findings:
        output.append(f"- **{finding.title}** - {finding.detail}")
        output.append(
            f"  - Evidence: {_evidence_link(finding, source_url, source_ref)}"
        )
        if finding.command:
            output.append(f"  - Command: `{finding.command}`")
            if finding.title == "Setup command":
                output.append("  - Review this command before running it.")
        if finding.evidence.text:
            excerpt = finding.evidence.text.replace("\\", "\\\\").replace("`", "\\`")
            output.append(f"  - Source: `{excerpt}`")
    output.append("")
    return output


def render_markdown(analysis: Analysis) -> str:
    """Render an analysis as a report with repository-relative evidence links."""
    output = [
        "# First PR Compass report",
        "",
        "> Read-only local analysis. Suggestions are evidence-based leads, not guarantees.",
        "",
    ]
    if analysis.source_url and analysis.source_ref:
        output.extend(
            [
                f"Repository: [{analysis.source_url}]({analysis.source_url})",
                f"Analyzed ref: `{analysis.source_ref}`",
                "",
            ]
        )
    output.extend(
        _render_section(
            "Setup steps",
            analysis.setup_steps,
            "No documented setup instructions or install commands were detected.",
            analysis.source_url,
            analysis.source_ref,
        )
    )
    output.extend(
        _render_section(
            "Tests",
            analysis.test_commands,
            "No recognized test command was detected. Check the project documentation manually.",
            analysis.source_url,
            analysis.source_ref,
        )
    )
    output.extend(
        _render_section(
            "Contribution instructions",
            analysis.contribution_guidance,
            "No contribution guidance lines were detected.",
            analysis.source_url,
            analysis.source_ref,
        )
    )
    output.extend(
        _render_section(
            "Starter task candidates",
            analysis.starter_tasks,
            "No TODO/FIXME/XXX markers were detected in supported source files. No task was invented.",
            analysis.source_url,
            analysis.source_ref,
        )
    )
    output.extend(["## Scan notes", ""])
    if analysis.warnings:
        output.extend(f"- {warning}" for warning in analysis.warnings)
    else:
        output.append("No scan warnings.")
    output.append("")
    return "\n".join(output)


def render_json(analysis: Analysis) -> str:
    """Render an analysis as stable, indented JSON."""
    return json.dumps(asdict(analysis), indent=2, ensure_ascii=False) + "\n"
