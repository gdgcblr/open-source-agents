"""Report formatters for terminal, JSON, Markdown, and GitHub annotations."""

from __future__ import annotations

import json
from typing import Any

from merge_ready.model import Severity, ValidationReport, Verdict


def format_terminal(report: ValidationReport, use_color: bool = True) -> str:
    """Format the validation report for readable terminal display."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f"  MergeReady Contribution Validator — {report.category}/{report.slug}")
    if report.base_ref:
        lines.append(f"  Target Base Reference: {report.base_ref}")
    lines.append("=" * 72)
    lines.append("")

    # Rule verdicts
    for rule_id, res in report.results.items():
        tag = f"[{res.verdict.value}]"
        reason_suffix = f" ({res.reason})" if res.reason else ""
        lines.append(f"  {tag:<8} {res.rule_id}: {res.name}{reason_suffix}")

        for f in res.findings:
            sev_tag = f"[{f.severity.value}]"
            loc = f"{f.path}:{f.line}" if f.path and f.line else (f.path or "")
            loc_str = f" in {loc}" if loc else ""
            lines.append(f"    - {sev_tag} {f.message}{loc_str}")
            if f.evidence:
                lines.append(f"        Evidence: {f.evidence}")
            if f.source_rule:
                lines.append(f"        Requirement: {f.source_rule}")
            if f.fix:
                lines.append(f"        Fix: {f.fix}")

    lines.append("")
    lines.append("-" * 72)
    s = report.summary
    summary_line = (
        f"Summary: {s.get('pass', 0)} pass · {s.get('fail', 0)} fail · "
        f"{s.get('error', 0)} error · {s.get('warn', 0)} warn · "
        f"{s.get('skip', 0)} skipped · {s.get('na', 0)} n/a"
    )
    lines.append(summary_line)

    if report.has_execution_errors:
        lines.append("Result: ERROR — Validator execution encountered runtime or configuration errors.")
    elif report.has_failures:
        lines.append("Result: FAILED — Please resolve errors before submitting your pull request.")
    elif report.has_warnings:
        lines.append("Result: PASSED WITH WARNINGS — Review recommendations before opening PR.")
    else:
        lines.append("Result: PASSED — Contribution meets all checked repository standards.")
    lines.append("-" * 72)

    return "\n".join(lines)


def format_json(report: ValidationReport) -> str:
    """Return strictly valid JSON string representation of the report."""
    return json.dumps(report.to_dict(), indent=2)


def format_markdown(report: ValidationReport) -> str:
    """Format report in GitHub-flavored Markdown for PR comments or Job Summaries."""
    lines: list[str] = []
    lines.append(f"# MergeReady Validation Report: `{report.category}/{report.slug}`\n")
    if report.base_ref:
        lines.append(f"**Base Git Reference**: `{report.base_ref}`\n")

    s = report.summary
    if report.has_execution_errors:
        status_emoji = "💥 **VALIDATOR ERROR**"
    elif report.has_failures:
        status_emoji = "❌ **FAILED**"
    elif report.has_warnings:
        status_emoji = "⚠️ **PASSED WITH WARNINGS**"
    else:
        status_emoji = "✅ **PASSED**"

    lines.append(f"### Verdict: {status_emoji}\n")

    lines.append("| Metric | Count |")
    lines.append("| :--- | :--- |")
    lines.append(f"| Passed Rules | {s.get('pass', 0)} |")
    lines.append(f"| Failing Rules | {s.get('fail', 0)} |")
    lines.append(f"| Execution Error Rules | {s.get('error', 0)} |")
    lines.append(f"| Warning Rules | {s.get('warn', 0)} |")
    lines.append(f"| Skipped Rules | {s.get('skip', 0)} |")
    lines.append(f"| Total Findings | {s.get('findings_total', 0)} (Errors: {s.get('errors', 0)}, Warnings: {s.get('warnings', 0)}) |\n")

    # Detailed findings table if any findings exist
    all_findings = []
    for res in report.results.values():
        all_findings.extend(res.findings)

    if all_findings:
        lines.append("### Detailed Findings\n")
        lines.append("| Rule | Severity | File & Location | Description & Fix |")
        lines.append("| :--- | :--- | :--- | :--- |")
        for f in all_findings:
            loc = f"`{f.path}:{f.line}`" if f.path and f.line else (f"`{f.path}`" if f.path else "—")
            fix_part = f"<br/>*Fix:* {f.fix}" if f.fix else ""
            ev_part = f"<br/>*Evidence:* `{f.evidence}`" if f.evidence else ""
            desc = f"{f.message}{ev_part}{fix_part}"
            lines.append(f"| **{f.rule_id}** | `{f.severity.value}` | {loc} | {desc} |")
        lines.append("")

    lines.append("### Checked Rules Overview\n")
    lines.append("| Rule ID | Rule Name | Verdict | Notes |")
    lines.append("| :--- | :--- | :--- | :--- |")
    for res in report.results.values():
        if res.verdict == Verdict.PASS:
            badge = "✅ PASS"
        elif res.verdict == Verdict.FAIL:
            badge = "❌ FAIL"
        elif res.verdict == Verdict.ERROR:
            badge = "💥 ERROR"
        elif res.verdict == Verdict.WARN:
            badge = "⚠️ WARN"
        elif res.verdict == Verdict.SKIP:
            badge = "⏭️ SKIP"
        else:
            badge = "⚪ N/A"
        note = res.reason or (f"{len(res.findings)} finding(s)" if res.findings else "Clean")
        lines.append(f"| **{res.rule_id}** | {res.name} | {badge} | {note} |")

    lines.append("\n---\n*Report generated by MergeReady contribution validator.*")
    return "\n".join(lines)


def format_github_annotations(report: ValidationReport) -> str:
    """Format findings as GitHub Actions workflow commands (inline annotations)."""
    lines: list[str] = []
    for res in report.results.values():
        for f in res.findings:
            if f.severity == Severity.INFO:
                cmd = "notice"
            elif f.severity == Severity.WARNING:
                cmd = "warning"
            else:
                cmd = "error"

            attrs = []
            if f.path:
                attrs.append(f"file={f.path}")
            if f.line:
                attrs.append(f"line={f.line}")
            attr_str = f" {','.join(attrs)}" if attrs else ""

            msg = f.message
            if f.fix:
                msg += f" (Fix: {f.fix})"
            lines.append(f"::{cmd}{attr_str}::[{f.rule_id}] {msg}")
    return "\n".join(lines)
