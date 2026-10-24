"""Main Streamlit dashboard layout and tab views for MergeMesh."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import streamlit as st

from domain.models import AnalysisReport, ScenarioDefinition
from services.report_export import export_report_to_json, export_report_to_markdown
from ui.components import (
    render_dependency_graph,
    render_finding_card,
    render_test_result_block,
)


def _compute_run_status_label(report: AnalysisReport | None, error_msg: str | None) -> str:
    if error_msg:
        return "Error"
    if report is None:
        return "Ready"
    if report.ai_explanation.status in {"FALLBACK", "UNAVAILABLE"}:
        return "Completed with AI fallback"
    return "Completed"


def render_overview_tab(
    report: AnalysisReport,
    on_apply_fix: Callable[[], None],
    on_switch_safe: Callable[[], None] | None = None,
) -> None:
    """Render the Overview tab with summary cards, finding headline, dependency graph, and fix actions."""
    isolated_tests = [t for t in report.test_results if t.test_kind in {"provider_isolated", "consumer_isolated"}]
    isolated_passed = sum(1 for t in isolated_tests if t.status == "PASS")
    combined_test = next((t for t in report.test_results if t.test_kind == "combined_integration"), None)
    post_fix = report.post_fix_result

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        iso_label = f"{isolated_passed} / {len(isolated_tests)} Passed" if isolated_tests else "Not Configured"
        iso_color = "#4ade80" if isolated_tests and isolated_passed == len(isolated_tests) else "#94a3b8"
        st.markdown(
            f"""
            <div class="mm-card">
                <div class="mm-metric-label">Isolated PR Checks</div>
                <div class="mm-metric-value" style="color:{iso_color};">{iso_label}</div>
                <div style="font-size:0.78rem; color:#94a3b8;">{'Consumer unit test uses mock' if any(t.uses_stale_mock for t in isolated_tests) else 'Per-repository unit tests'}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        comb_status = combined_test.status if combined_test else "NOT_RUN"
        comb_color = "#f87171" if comb_status == "FAIL" else ("#4ade80" if comb_status == "PASS" else "#fbbf24")
        st.markdown(
            f"""
            <div class="mm-card">
                <div class="mm-metric-label">Combined Candidate Check</div>
                <div class="mm-metric-value" style="color:{comb_color};">{comb_status}</div>
                <div style="font-size:0.78rem; color:#94a3b8;">{combined_test.failure_summary if (combined_test and combined_test.failure_summary) else ('Static analysis only' if comb_status == 'NOT_RUN' else 'Live provider -> consumer')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        affected_consumers = len({f.consumer_repo for f in report.finding_list})
        aff_color = "#f87171" if affected_consumers > 0 and not (post_fix and post_fix.status == "PASS") else "#4ade80"
        st.markdown(
            f"""
            <div class="mm-card">
                <div class="mm-metric-label">Consumers Affected</div>
                <div class="mm-metric-value" style="color:{aff_color};">{affected_consumers} ({report.consumer_repo if affected_consumers else 'None'})</div>
                <div style="font-size:0.78rem; color:#94a3b8;">{len(report.finding_list)} deterministic finding(s)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col4:
        pf_text = post_fix.status if post_fix else ("N/A (Compatible)" if not report.finding_list else "Not Run Yet")
        pf_color = "#4ade80" if pf_text in {"PASS", "N/A (Compatible)"} else "#94a3b8"
        st.markdown(
            f"""
            <div class="mm-card">
                <div class="mm-metric-label">Post-Fix Verification</div>
                <div class="mm-metric-value" style="color:{pf_color};">{pf_text}</div>
                <div style="font-size:0.78rem; color:#94a3b8;">Deterministic runtime check</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if report.consumer_mock_note:
        st.info(f"**Execution / Coverage Note:** {report.consumer_mock_note}")

    st.markdown("#### Compatibility Verdict & Findings")
    if report.finding_list:
        for f in report.finding_list:
            render_finding_card(f, post_fix_result=report.post_fix_result)
    else:
        st.markdown(
            f"""
            <div class="mm-card-pass">
                <strong>[VERIFIED COMPATIBLE] No Cross-Repository Contract Mismatches Detected</strong>
                <p style="margin:0.4rem 0 0 0; color:#e2e8f0;">
                    Contract comparison and consumer AST analysis between
                    <code>{report.provider_repo}</code> and <code>{report.consumer_repo}</code> detected no breaking changes.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("#### Cross-Repository Dependency Relationship")
    render_dependency_graph(report)

    act_col1, act_col2 = st.columns(2)
    with act_col1:
        if report.finding_list and not (report.post_fix_result and report.post_fix_result.status == "PASS"):
            if st.button(
                "Verify Suggested Fix (Run Remediated Consumer Integration Check)",
                type="primary",
                use_container_width=True,
            ):
                on_apply_fix()
        elif report.post_fix_result and report.post_fix_result.status == "PASS":
            st.success(
                f"Post-fix integration test (`{report.post_fix_result.file_path}`) executed and PASSED "
                f"in {report.post_fix_result.duration_ms} ms."
            )
    with act_col2:
        if on_switch_safe is not None and report.scenario_id == "customer_id_rename":
            if st.button("Switch to Scenario B (Compatible Optional Field)", use_container_width=True):
                on_switch_safe()


def render_pr_changes_tab(report: AnalysisReport, scenario: ScenarioDefinition | None = None) -> None:
    """Render side-by-side PR / Git revision diffs and source files."""
    if report.input_mode == "local_git_repos":
        st.caption(
            "Local Git Repository Mode: The diffs below are computed directly from the selected local Git repositories and revisions."
        )
    else:
        st.caption(
            "Bundled PR Fixture Mode: The diffs below are loaded from local repository fixtures (`fixtures/scenarios/`)."
        )

    col_a, col_b = st.columns(2)
    provider_diff = next((d for d in report.diffs if d.repo == report.provider_repo), None)
    consumer_diff = next((d for d in report.diffs if d.repo == report.consumer_repo), None)

    with col_a:
        st.markdown(f"#### Provider — `{report.provider_repo}`")
        st.markdown(f"**{report.pr_a_title}**")
        if provider_diff:
            st.caption(f"Path: `{provider_diff.path}`")
            if provider_diff.summary:
                st.write(provider_diff.summary)
            st.code(provider_diff.content, language="diff")

    with col_b:
        st.markdown(f"#### Consumer — `{report.consumer_repo}`")
        st.markdown(f"**{report.pr_b_title}**")
        if consumer_diff:
            st.caption(f"Path: `{consumer_diff.path}`")
            if consumer_diff.summary:
                st.write(consumer_diff.summary)
            st.code(consumer_diff.content, language="diff")

    if scenario and scenario.post_fix_consumer_source:
        with st.expander("View Suggested Consumer Remediation (`repos/checkout-client/client_fixed.py`)"):
            fixed_path = Path(scenario.scenario_dir) / scenario.post_fix_consumer_source
            if fixed_path.exists():
                st.code(fixed_path.read_text(encoding="utf-8"), language="python")


def render_contract_tab(report: AnalysisReport, scenario: ScenarioDefinition | None = None) -> None:
    """Render dependency graph, before/after contract comparison, and AST consumer accesses."""
    st.markdown("#### Service Dependency Topology")
    render_dependency_graph(report)

    comp = report.contract_comparison
    before_lang = "python" if comp.provider_before_path.lower().endswith(".py") else "json"
    after_lang = "python" if comp.provider_after_path.lower().endswith(".py") else "json"

    before_json_col, after_json_col = st.columns(2)
    with before_json_col:
        st.markdown(f"**Provider Contract Before (`{comp.provider_before_path}`)**")
        st.code(comp.before_raw_content, language=before_lang)
    with after_json_col:
        st.markdown(f"**Provider Contract After (`{comp.provider_after_path}`)**")
        st.code(comp.after_raw_content, language=after_lang)

    st.markdown("#### Deterministic Before / After Contract Field Comparison")
    field_rows = []
    for fc in comp.field_changes:
        field_rows.append(
            {
                "Field Path": fc.field_path,
                "Change Type": fc.change_type.upper(),
                "Before Type": fc.before_type or "—",
                "Before Sample": str(fc.before_value) if fc.before_value is not None else "—",
                "After Type": fc.after_type or "—",
                "After Sample": str(fc.after_value) if fc.after_value is not None else "—",
                "Candidate Replacement": fc.replacement_candidate or "—",
                "Compatibility Impact": fc.impact,
            }
        )
    st.dataframe(field_rows, use_container_width=True, hide_index=True)

    st.markdown("#### Detected Consumer Field Accesses (Python AST Scanner)")
    access_rows = []
    for acc in report.consumer_accesses:
        access_rows.append(
            {
                "Consumer Repo": acc.consumer_repo,
                "Source File": acc.file_path,
                "Line": acc.line,
                "Accessed Field": acc.field_path,
                "Access Style": acc.access_mode,
                "Default Value Provided": "Yes" if acc.default_provided else "No",
                "Measured Code Snippet": acc.code_snippet,
            }
        )
    st.dataframe(access_rows, use_container_width=True, hide_index=True)
    st.caption(
        "Scope Note: The deterministic analyzer extracts fields from JSON (.json) or Python (.py) provider contracts "
        "and scans Python AST dictionary subscripts (`payload['key']`) and `.get('key')` calls."
    )


def render_test_evidence_tab(
    report: AnalysisReport,
    on_rerun_tests: Callable[[], None],
    on_apply_fix: Callable[[], None],
) -> None:
    """Render executed test results, stdout/stderr logs, and report export actions."""
    top_col1, top_col2, top_col3 = st.columns([2, 2, 3])
    with top_col1:
        if st.button("Re-Run Analysis & Approved Tests", use_container_width=True):
            on_rerun_tests()
    with top_col2:
        if report.finding_list and not (report.post_fix_result and report.post_fix_result.status == "PASS"):
            if st.button("Run Post-Fix Verification Check", type="primary", use_container_width=True):
                on_apply_fix()
    with top_col3:
        json_str = export_report_to_json(report)
        md_str = export_report_to_markdown(report)
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "Download JSON Report",
                data=json_str,
                file_name=f"mergemesh_{report.scenario_id}_report.json",
                mime="application/json",
                use_container_width=True,
            )
        with dl2:
            st.download_button(
                "Download Markdown Report",
                data=md_str,
                file_name=f"mergemesh_{report.scenario_id}_report.md",
                mime="text/markdown",
                use_container_width=True,
            )

    st.markdown("#### Test Suite Execution Results")
    if not report.test_results:
        st.info(
            "No test files were configured for this run. Static contract and AST findings above are marked as "
            "`INFERRED_RISK` (unverified by runtime test execution). Configure and approve pytest paths in the sidebar to run tests."
        )
    else:
        for tr in report.test_results:
            render_test_result_block(tr)

    if report.post_fix_result:
        st.markdown("#### Post-Fix Remediated Execution Result")
        render_test_result_block(report.post_fix_result)

    if report.finding_list:
        st.markdown("#### Measured Evidence Records")
        ev_rows = []
        for f in report.finding_list:
            for ev in f.evidence:
                ev_rows.append(
                    {
                        "Evidence ID": ev.evidence_id,
                        "Kind": ev.kind,
                        "Repository": ev.repo or "—",
                        "File Path": ev.path or "—",
                        "Line": str(ev.line) if ev.line is not None else "—",
                        "Exit Code": str(ev.exit_code) if ev.exit_code is not None else "—",
                        "Measured Detail": ev.detail,
                    }
                )
        st.dataframe(ev_rows, use_container_width=True, hide_index=True)


def render_ai_explanation_tab(
    report: AnalysisReport,
    on_regenerate_ai: Callable[[], None],
) -> None:
    """Render the AI Explanation tab with honest distinction between Gemma Mode and Deterministic Fallback Mode."""
    ai = report.ai_explanation
    is_live_gemma = ai.status == "SUCCESS"

    if not is_live_gemma:
        st.warning(
            f"**Deterministic Fallback Mode Active (`status={ai.status}`) — Gemma Synthesis Was Unavailable**\n\n"
            f"- **Active Path:** `{ai.provider}` (Configured model: `{ai.model or 'none'}`)\n"
            f"- **Reason & Recovery:** {ai.fallback_reason or 'Local Ollama is not running; using deterministic rule engine.'}\n"
            f"- **Honest Labeling Notice:** The assessment below is synthesized by MergeMesh's deterministic rule engine from AST, contract diff, and test evidence — it was **not** generated by Gemma."
        )
    else:
        st.success(
            f"**Gemma Mode Active (`status=SUCCESS`)** — Generated via Google ADK | "
            f"Provider: `{ai.provider}` | Model: `{ai.model}` | Inference Latency: `{ai.duration_ms} ms`"
        )

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("#### 1. Deterministic Findings & Measured Evidence (Ground Truth)")
        st.markdown(
            """
            <div class="mm-card">
                <div class="mm-metric-label">Detection vs. Reasoning vs. Verification Boundary</div>
                <div style="font-size:0.9rem; color:#e2e8f0;">
                    Deterministic contract extractors and Python AST scanners detect field changes.
                    The opt-in pytest runner verifies runtime pass/fail results.
                    Gemma interprets this evidence but never overrides test verdicts.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if report.finding_list:
            st.markdown("**Deterministic Compatibility Findings:**")
            for f in report.finding_list:
                st.markdown(
                    f"- **`{f.finding_id}` (`{f.kind}`, `{f.verification_state}`)**: "
                    f"`{f.provider_repo}` &rarr; `{f.consumer_repo}` on field `{f.field}` "
                    f"(candidate replacement: `{f.replacement_candidate or 'None'}`)"
                )
        else:
            st.markdown("- **Deterministic Verdict:** `0` breaking contract findings detected.")

        st.markdown("**Observed Facts (Backed by Repository Paths & Executed Tests):**")
        for fact in ai.observed_facts:
            st.markdown(f"- {fact}")

        if report.source_hashes:
            with st.expander("View Input File / Revision SHA-256 Hashes"):
                st.json(report.source_hashes)

    with col_right:
        right_header = (
            f"#### 2. Gemma AI Reasoning & Remediation (`{ai.model}`)"
            if is_live_gemma
            else "#### 2. Deterministic Rule-Based Assessment (Fallback — Not Model-Generated)"
        )
        source_badge = (
            f"AI Model: {ai.model}"
            if is_live_gemma
            else f"Fallback Engine ({ai.status})"
        )
        st.markdown(right_header)
        compat_html = (
            f'<h5 style="margin:0.75rem 0 0.35rem 0; color:#f8fafc;">Compatibility Assessment</h5>'
            f'<p style="font-size:0.93rem; color:#cbd5e1;">{ai.compatibility_assessment}</p>'
            if ai.compatibility_assessment
            else ""
        )
        st.markdown(
            f"""
            <div class="mm-ai-box">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.4rem;">
                    <span class="mm-badge mm-badge-info">{source_badge}</span>
                    <div>
                        <span class="mm-badge mm-badge-warn">Risk Severity: {ai.severity_label.upper()}</span>
                        <span class="mm-badge mm-badge-fixture" style="margin-left:0.35rem;">Confidence: {ai.confidence_label.upper()}</span>
                    </div>
                </div>
                <h5 style="margin:0.75rem 0 0.35rem 0; color:#f8fafc;">Summary</h5>
                <p style="font-size:0.93rem; color:#e2e8f0;">{ai.summary}</p>
                {compat_html}
                <h5 style="margin:0.75rem 0 0.35rem 0; color:#f8fafc;">Downstream Impact</h5>
                <p style="font-size:0.93rem; color:#cbd5e1;">{ai.why_it_matters}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if ai.hypotheses:
            st.markdown("**Inferred Hypotheses & Remaining Uncertainty:**")
            for hyp in ai.hypotheses:
                st.markdown(f"- *(Hypothesis)* {hyp}")

        st.markdown("**Suggested Context-Specific Remediation Options:**")
        for opt in ai.suggested_fix_options:
            st.markdown(f"- {opt}")

        if ai.remediation_tradeoffs:
            st.markdown("**Consumer Update vs. Provider Backward-Compatibility Trade-offs:**")
            st.markdown(f"> {ai.remediation_tradeoffs}")

        if ai.verification_plan:
            st.markdown("**Verification Plan:**")
            for step in ai.verification_plan:
                st.markdown(f"- {step}")

        if ai.suggested_test:
            st.markdown("**Suggested Targeted Contract Test (Text Suggestion Only — Not Auto-Executed):**")
            st.code(ai.suggested_test, language="python")

        if ai.limitations:
            st.caption("**Limitations & Scope:** " + " | ".join(ai.limitations))

        if st.button("Regenerate Explanation", use_container_width=True):
            on_regenerate_ai()
