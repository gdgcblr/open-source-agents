"""Deterministic Markdown and JSON report renderers (Report Composer)."""

from __future__ import annotations

from patchproof.core.models import VerificationReport
from patchproof.core.validator import assert_valid_report


class ReportComposer:
    """Deterministic component that renders validated VerificationReports to JSON and Markdown."""

    def render_json(self, report: VerificationReport, *, indent: int = 2) -> str:
        """Validate and serialize a VerificationReport to formatted JSON."""
        assert_valid_report(report)
        return report.model_dump_json(indent=indent)

    def render_markdown(self, report: VerificationReport) -> str:
        """Validate and render a VerificationReport to human-readable Markdown."""
        assert_valid_report(report)
        lines: list[str] = []

        lines.append("# PatchProof Verification Report")
        lines.append("")
        lines.append(f"- **Run ID**: `{report.run_id}`")
        lines.append(f"- **Schema Version**: `{report.schema_version}`")
        lines.append(f"- **Created At**: `{report.created_at}`")
        lines.append(f"- **Source Kind**: `{report.source.kind.value}`")
        lines.append(f"- **Repository / Fixture**: `{report.source.repository}`")
        lines.append(f"- **Synthetic Fixture**: `{report.source.synthetic}`")
        lines.append(f"- **Snapshot Hash**: `{report.source.snapshot_hash}`")
        lines.append(f"- **Truncated**: `{report.source.truncated}`")
        lines.append(f"- **Advisory Verdict**: **`{report.verdict.value}`**")
        lines.append("")
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(report.summary)
        lines.append("")

        lines.append("## Requirements & Traceability")
        lines.append("")
        if not report.requirements:
            lines.append("_No requirements extracted._")
        else:
            lines.append(
                "| Requirement ID | Origin | Status | Requirement | "
                "Code Locations | Tests | Evidence IDs |"
            )
            lines.append("|---|---|---|---|---|---|---|")
            for req in report.requirements:
                locs = (
                    ", ".join(
                        f"`{loc.path}:{loc.line_start}-{loc.line_end}`"
                        if loc.line_start
                        else f"`{loc.path}`"
                        for loc in req.code_locations
                    )
                    or "none"
                )
                tests = ", ".join(f"`{t}`" for t in req.test_ids) or "none"
                evs = ", ".join(f"`{e}`" for e in req.evidence_ids) or "none"
                lines.append(
                    f"| `{req.requirement_id}` | `{req.origin.value}` | "
                    f"**`{req.status.value}`** | {req.text} | {locs} | {tests} | {evs} |"
                )
        lines.append("")

        lines.append("## Findings (Confirmed vs. Hypotheses)")
        lines.append("")
        if not report.findings:
            lines.append("_No findings recorded._")
        else:
            for f in report.findings:
                req_str = ", ".join(f"`{r}`" for r in f.requirement_ids) or "none"
                ev_str = ", ".join(f"`{e}`" for e in f.evidence_ids) or "none"
                lines.append(
                    f"### `{f.finding_id}` [{f.status.value}] {f.title} "
                    f"(Category: `{f.category.value}`, Severity: `{f.severity.value}`, "
                    f"Confidence: `{f.confidence.value}`)"
                )
                lines.append(f"- **Description**: {f.description}")
                lines.append(f"- **Requirement IDs**: {req_str}")
                lines.append(f"- **Evidence IDs**: {ev_str}")
                lines.append(f"- **Recommended Action**: {f.recommended_action}")
                if f.disproof_criteria:
                    lines.append(f"- **Disproof Criteria**: {f.disproof_criteria}")
                lines.append("")

        lines.append("## Verification Checks")
        lines.append("")
        if not report.checks:
            lines.append("_No checks requested._")
        else:
            lines.append(
                "| Check ID | Name | Status | Profile | Exit Code | "
                "Evidence IDs | Details / Reason Not Run |"
            )
            lines.append("|---|---|---|---|---|---|---|")
            for c in report.checks:
                exit_str = str(c.exit_code) if c.exit_code is not None else "N/A"
                ev_str = ", ".join(f"`{e}`" for e in c.evidence_ids) or "none"
                detail = c.reason_not_run or (c.output_excerpt or "")
                lines.append(
                    f"| `{c.check_id}` | `{c.name}` | **`{c.status.value}`** | "
                    f"`{c.command_profile}` | `{exit_str}` | {ev_str} | {detail} |"
                )
        lines.append("")

        if report.test_proposals:
            lines.append("## Proposed Verification Tests")
            lines.append("")
            for tp in report.test_proposals:
                lines.append(
                    f"- **`{tp.proposal_id}` (`{tp.name}`)** for `{tp.requirement_id}`: "
                    f"{tp.input_summary} -> Expected: {tp.expected_outcome}"
                )
            lines.append("")

        lines.append("## Agent Execution Summary")
        lines.append("")
        for arun in report.agent_runs:
            lines.append(
                f"- **`{arun.agent_name}`** (`{arun.status.value}`, `{arun.duration_ms}ms`): "
                f"{arun.summary}"
            )
        lines.append("")

        lines.append("## Evidence Ledger")
        lines.append("")
        for ev in report.evidence:
            loc_suffix = (
                f" (`{ev.path}:{ev.line_start}-{ev.line_end}`)"
                if ev.path and ev.line_start
                else (f" (`{ev.path}`)" if ev.path else "")
            )
            redacted_tag = " `[REDACTED]`" if ev.redacted else ""
            lines.append(
                f"- **`{ev.evidence_id}`** [`{ev.kind.value}` | `{ev.trust_level.value}`]"
                f"{loc_suffix} -- `{ev.content_hash}`{redacted_tag}"
            )
        lines.append("")

        lines.append("## Limitations & Unverified Risks")
        lines.append("")
        if not report.limitations:
            lines.append("- None recorded.")
        else:
            for lim in report.limitations:
                lines.append(f"- {lim}")
        lines.append("")

        if report.open_questions:
            lines.append("## Open Questions")
            lines.append("")
            for q in report.open_questions:
                lines.append(f"- {q}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"
