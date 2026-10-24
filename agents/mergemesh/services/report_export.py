"""JSON and Markdown report export utilities for MergeMesh."""

from __future__ import annotations

import json
from pathlib import Path

from config.settings import REPORTS_ROOT
from domain.models import AnalysisReport


def export_report_to_json(report: AnalysisReport) -> str:
    """Serialize an AnalysisReport to formatted JSON."""
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def export_report_to_markdown(report: AnalysisReport) -> str:
    """Format an AnalysisReport as a developer-friendly Markdown document."""
    input_mode_desc = (
        "Local Git repositories (`local_git_repos`)."
        if report.input_mode == "local_git_repos"
        else "Bundled local PR fixture (`simulated_fixture`)."
    )
    ai = report.ai_explanation
    is_live_gemma = ai.status == "SUCCESS"
    section3_title = (
        f"## 3. Gemma AI Reasoning & Remediation (`{ai.model}`)"
        if is_live_gemma
        else f"## 3. Deterministic Fallback Assessment (`status={ai.status}` — Not Model-Generated)"
    )

    lines: list[str] = [
        f"# MergeMesh Compatibility Report — `{report.scenario_id}`",
        "",
        f"> **Input Mode:** {input_mode_desc} No external cloud API call was made.",
        "",
        f"- **Run ID:** `{report.run_id}`",
        f"- **Timestamp (UTC):** `{report.created_at}`",
        f"- **Provider Repo:** `{report.provider_repo}` ({report.pr_a_title})",
        f"- **Consumer Repo:** `{report.consumer_repo}` ({report.pr_b_title})",
        f"- **Overall Verdict:** **{report.overall_status}**",
        f"- **Explanation Mode:** `{ai.provider}` (`status={ai.status}`, `model={ai.model}`)",
        "",
        "---",
        "",
        "## 1. Executed Test Evidence",
        "",
        "| Check | Kind | Status | Exit Code | Duration (ms) | File Path | Notes |",
        "|---|---|---|---:|---:|---|---|",
    ]
    for tr in report.test_results:
        note = "Uses stale mock" if tr.uses_stale_mock else (tr.failure_summary or "Passed")
        lines.append(
            f"| {tr.label} | `{tr.test_kind}` | **{tr.status}** | `{tr.exit_code}` | {tr.duration_ms} | `{tr.file_path}` | {note} |"
        )
    if report.post_fix_result:
        pf = report.post_fix_result
        lines.append(
            f"| {pf.label} | `{pf.test_kind}` | **{pf.status}** | `{pf.exit_code}` | {pf.duration_ms} | `{pf.file_path}` | Remediated consumer check |"
        )

    lines.extend(["", "## 2. Deterministic Compatibility Findings", ""])
    if not report.finding_list:
        lines.append("No breaking compatibility findings detected. Candidate changes are compatible.")
    else:
        for f in report.finding_list:
            lines.extend(
                [
                    f"### [{f.severity}] `{f.finding_id}` — {f.kind}",
                    f"- **Verification State:** `{f.verification_state}`",
                    f"- **Summary:** {f.summary}",
                    f"- **Incompatible Field:** `{f.field}`"
                    + (f" (Candidate replacement: `{f.replacement_candidate}`)" if f.replacement_candidate else ""),
                    f"- **Suggested Remediation:** {f.suggested_remediation}",
                    "- **Measured Evidence:**",
                ]
            )
            for ev in f.evidence:
                loc = f"`{ev.path}:{ev.line}`" if ev.line else f"`{ev.path}`"
                lines.append(f"  - `[{ev.kind}]` ({loc}): {ev.detail}")
            lines.append("")

    lines.extend(
        [
            section3_title,
            "",
            f"> **Source:** {ai.provider} | **Status:** `{ai.status}` | **Severity:** `{ai.severity_label}` | **Confidence:** `{ai.confidence_label}`",
            "",
        ]
    )
    if not is_live_gemma and ai.fallback_reason:
        lines.extend([f"> **Fallback Reason:** {ai.fallback_reason}", ""])

    lines.append(f"**Summary:** {ai.summary}")
    lines.append("")
    if ai.compatibility_assessment:
        lines.append(f"**Compatibility Assessment:** {ai.compatibility_assessment}")
        lines.append("")
    lines.append(f"**Downstream Impact:** {ai.why_it_matters}")
    lines.append("")
    lines.append("**Suggested Fix Options:**")
    for opt in ai.suggested_fix_options:
        lines.append(f"- {opt}")
    if ai.remediation_tradeoffs:
        lines.extend(["", f"**Trade-offs (Consumer vs. Provider):** {ai.remediation_tradeoffs}"])
    if ai.verification_plan:
        lines.extend(["", "**Verification Plan:**"])
        for step in ai.verification_plan:
            lines.append(f"- {step}")

    return "\n".join(lines) + "\n"


def save_report_artifacts(
    report: AnalysisReport,
    reports_root: Path = REPORTS_ROOT,
) -> tuple[Path, Path]:
    """Write JSON and Markdown report files to the reports directory."""
    reports_root.mkdir(parents=True, exist_ok=True)
    json_path = reports_root / f"report_{report.scenario_id}.json"
    md_path = reports_root / f"report_{report.scenario_id}.md"
    json_path.write_text(export_report_to_json(report), encoding="utf-8")
    md_path.write_text(export_report_to_markdown(report), encoding="utf-8")
    return json_path, md_path
