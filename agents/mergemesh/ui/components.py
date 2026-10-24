"""Reusable Streamlit UI components for MergeMesh."""

from __future__ import annotations

import streamlit as st

from config.settings import AppSettings, ProviderReadiness
from domain.models import AnalysisReport, Finding, TestExecutionResult


def render_header(
    settings: AppSettings,
    run_status: str,
    input_mode: str = "simulated_fixture",
    ai_status: str | None = None,
) -> None:
    """Render the top MergeMesh identity header and status pills."""
    active_model_label = settings.gemini_model if settings.ai_mode == "gemini" else settings.ollama_model
    if settings.ai_mode == "deterministic" or ai_status == "SKIPPED":
        ai_badge_text = "Operating Mode: Deterministic Only (No LLM)"
        ai_badge_cls = "mm-badge-info"
    elif ai_status == "SUCCESS":
        ai_badge_text = f"Operating Mode: Gemma Active ({active_model_label})"
        ai_badge_cls = "mm-badge-pass"
    elif ai_status in {"FALLBACK", "UNAVAILABLE"}:
        ai_badge_text = f"Operating Mode: Deterministic Fallback ({active_model_label} Unavailable)"
        ai_badge_cls = "mm-badge-warn"
    else:
        ai_badge_text = f"Configured Mode: Gemma ({active_model_label})"
        ai_badge_cls = "mm-badge-info"

    input_badge_text = (
        "Input: Local Git Repositories"
        if input_mode == "local_git_repos"
        else "Input: Bundled PR Fixtures"
    )

    status_class = "mm-badge-info"
    if "Fallback" in run_status or "Warn" in run_status:
        status_class = "mm-badge-warn"
    elif "Completed" in run_status:
        status_class = "mm-badge-pass"
    elif "Error" in run_status:
        status_class = "mm-badge-fail"

    st.markdown(
        f"""
        <div class="mm-header">
            <div>
                <div class="mm-title">MergeMesh</div>
                <div class="mm-subtitle">Catch cross-repository failures before merge — Deterministic contract analysis &amp; Gemma compatibility reasoning</div>
            </div>
            <div class="mm-badge-row">
                <span class="mm-badge mm-badge-fixture">{input_badge_text}</span>
                <span class="mm-badge {ai_badge_cls}">{ai_badge_text}</span>
                <span class="mm-badge {status_class}">Status: {run_status}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_provider_readiness_sidebar(readiness: ProviderReadiness, settings: AppSettings) -> None:
    """Render honest local runtime readiness indicators in the sidebar."""
    st.sidebar.markdown("### Local Runtime Status")
    st.sidebar.caption("**Deterministic Engine:** [READY] Active (Python AST + Contract Diff + Pytest)")
    ollama_icon = "[READY]" if (readiness.ollama_reachable and readiness.ollama_model_installed) else "[OFFLINE]"
    st.sidebar.caption(f"**Local Ollama ({settings.ollama_model}):** {ollama_icon} {readiness.ollama_status_message}")
    if readiness.ollama_recovery_hint:
        st.sidebar.caption(f"**Recovery Hint:** {readiness.ollama_recovery_hint}")
    gemini_icon = "[READY]" if readiness.gemini_configured else "[NOT CONFIGURED]"
    st.sidebar.caption(f"**Hosted Gemma ({settings.gemini_model}):** {gemini_icon} {readiness.gemini_status_message}")
    st.sidebar.caption(
        f"**Fallback Policy:** `ALLOW_LOCAL_FALLBACK={str(settings.allow_local_fallback).lower()}`"
    )


def render_dependency_graph(report: AnalysisReport) -> None:
    """Render the provider -> consumer dependency graph using Graphviz or HTML fallback."""
    post_fix_ok = bool(report.post_fix_result and report.post_fix_result.status == "PASS")
    has_breaking = any(f.severity in {"CRITICAL", "HIGH"} for f in report.finding_list) and not post_fix_ok

    try:
        st.graphviz_chart(report.graph_dot, use_container_width=True)
    except Exception:
        pass

    if has_breaking and report.finding_list:
        f0 = report.finding_list[0]
        if f0.replacement_candidate:
            mismatch_text = f"BREAKING MISMATCH: {f0.field} -&gt; {f0.replacement_candidate}"
        else:
            mismatch_text = f"BREAKING MISMATCH: {f0.field} ({f0.kind})"
        edge_badge = f'<span class="mm-badge mm-badge-fail">{mismatch_text}</span>'
    elif post_fix_ok:
        edge_badge = '<span class="mm-badge mm-badge-pass">REMEDIATED CONTRACT: VERIFIED PASS</span>'
    else:
        edge_badge = '<span class="mm-badge mm-badge-pass">COMPATIBLE REST JSON CONTRACT</span>'

    st.markdown(
        f"""
        <div class="mm-card" style="display:flex; align-items:center; justify-content:space-around; flex-wrap:wrap; gap:0.75rem; text-align:center;">
            <div>
                <div class="mm-metric-label">Provider Repository</div>
                <div class="mm-metric-value" style="color:#38bdf8;">{report.provider_repo}</div>
                <div style="font-size:0.8rem; color:#94a3b8;">{report.pr_a_title}</div>
            </div>
            <div style="font-family:Consolas,monospace; font-size:0.9rem;">
                <div>provides REST JSON payload &rarr;</div>
                <div style="margin-top:0.35rem;">{edge_badge}</div>
            </div>
            <div>
                <div class="mm-metric-label">Consumer Repository</div>
                <div class="mm-metric-value" style="color:#f8fafc;">{report.consumer_repo}</div>
                <div style="font-size:0.8rem; color:#94a3b8;">{report.pr_b_title}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_finding_card(finding: Finding, post_fix_result: TestExecutionResult | None = None) -> None:
    """Render a deterministic finding card distinguishing reproduced failures from inferred risks."""
    if post_fix_result and post_fix_result.status == "PASS":
        st.markdown(
            f"""
            <div class="mm-card-pass">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;">
                    <strong>[REMEDIATED — POST-FIX TEST PASSED] {finding.finding_id}</strong>
                    <span class="mm-badge mm-badge-pass">Verified Compatible After Fix</span>
                </div>
                <p style="margin:0.5rem 0 0.25rem 0; color:#e2e8f0;">
                    Original mismatch on field <code>{finding.field}</code> &rarr; <code>{finding.replacement_candidate or 'N/A'}</code>
                    was resolved by updating <code>{finding.consumer_repo}</code> and verified by executing
                    <code>{post_fix_result.file_path}</code> (exit code <code>{post_fix_result.exit_code}</code>).
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    ver_badge = (
        '<span class="mm-badge mm-badge-fail">REPRODUCED INTEGRATION FAILURE (Executed Test Failed)</span>'
        if finding.verification_state == "REPRODUCED_FAILURE"
        else '<span class="mm-badge mm-badge-warn">POTENTIAL COMPATIBILITY ISSUE (Static / Unverified Risk)</span>'
    )
    card_cls = "mm-card-fail" if finding.verification_state == "REPRODUCED_FAILURE" else "mm-card-warn"

    st.markdown(
        f"""
        <div class="{card_cls}">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem;">
                <div>
                    <span class="mm-badge mm-badge-fail">Prototype Severity: {finding.severity}</span>
                    <strong style="margin-left:0.5rem; font-size:1.05rem;">{finding.kind} ({finding.finding_id})</strong>
                </div>
                {ver_badge}
            </div>
            <p style="margin:0.65rem 0 0.4rem 0; font-size:0.98rem; color:#f8fafc;">{finding.summary}</p>
            <div style="font-family:Consolas,monospace; font-size:0.86rem; color:#cbd5e1; margin-top:0.35rem;">
                Provider: <code>{finding.provider_repo}</code> &nbsp;|&nbsp;
                Consumer: <code>{finding.consumer_repo}</code> &nbsp;|&nbsp;
                Removed/Changed Field: <code>{finding.field}</code> &nbsp;|&nbsp;
                Candidate Replacement: <code>{finding.replacement_candidate or 'None'}</code>
            </div>
            <div style="margin-top:0.55rem; font-size:0.88rem; color:#fde68a;">
                <strong>Suggested Remediation (for service owner review):</strong> {finding.suggested_remediation}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_test_result_block(tr: TestExecutionResult) -> None:
    """Render an executed test result with its real exit code, duration, and captured output."""
    status_badge_map = {
        "PASS": ('<span class="mm-badge mm-badge-pass">PASS (Executed)</span>', "mm-card-pass"),
        "FAIL": ('<span class="mm-badge mm-badge-fail">FAIL (Executed)</span>', "mm-card-fail"),
        "ERROR": ('<span class="mm-badge mm-badge-warn">ERROR (Runner/Setup)</span>', "mm-card-warn"),
        "TIMEOUT": ('<span class="mm-badge mm-badge-warn">TIMEOUT</span>', "mm-card-warn"),
        "NOT_RUN": ('<span class="mm-badge mm-badge-fixture">NOT RUN</span>', "mm-card"),
    }
    badge_html, card_cls = status_badge_map.get(tr.status, ('<span class="mm-badge">UNKNOWN</span>', "mm-card"))

    mock_tag = (
        '<span class="mm-badge mm-badge-warn" style="margin-left:0.4rem;">Uses Stale Mock Fixture</span>'
        if tr.uses_stale_mock
        else ""
    )

    st.markdown(
        f"""
        <div class="{card_cls}">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem;">
                <div>
                    <strong>{tr.label}</strong> {mock_tag}
                    <div style="font-family:Consolas,monospace; font-size:0.8rem; color:#94a3b8; margin-top:0.15rem;">
                        File: <code>{tr.file_path}</code> &nbsp;|&nbsp;
                        Exit Code: <code>{tr.exit_code}</code> &nbsp;|&nbsp;
                        Duration: <code>{tr.duration_ms} ms</code>
                    </div>
                </div>
                <div>{badge_html}</div>
            </div>
            {f'<div style="margin-top:0.5rem; font-family:Consolas,monospace; font-size:0.88rem; color:#fca5a5;"><strong>Observed Exception / Note:</strong> {tr.failure_summary}</div>' if tr.failure_summary else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander(f"View captured pytest output for `{tr.file_path}` (exit_code={tr.exit_code})", expanded=(tr.status == "FAIL")):
        output_text = (tr.stdout or "").strip()
        if tr.stderr and tr.stderr.strip():
            output_text += "\n--- STDERR ---\n" + tr.stderr.strip()
        st.code(output_text or "(no stdout/stderr captured)", language="text")
