"""MergeMesh — Cross-Repository Compatibility Analyzer (Streamlit Entry Point)."""

from __future__ import annotations

import hashlib
import streamlit as st

from config.settings import check_provider_readiness, load_settings
from services.analyze_service import (
    CustomRepoAnalysisRequest,
    compute_analysis_cache_key,
    run_custom_repo_analysis,
    run_scenario_analysis,
)
from services.report_export import save_report_artifacts
from services.scenario_loader import list_available_scenarios, load_scenario_definition
from ui.components import render_header, render_provider_readiness_sidebar
from ui.layout import (
    _compute_run_status_label,
    render_ai_explanation_tab,
    render_contract_tab,
    render_overview_tab,
    render_pr_changes_tab,
    render_test_evidence_tab,
)
from ui.styles import DASHBOARD_CSS


def main() -> None:
    st.set_page_config(
        page_title="MergeMesh — Cross-Repository Compatibility Analyzer",
        page_icon="🔗",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)

    # Initialize session state
    if "source_mode" not in st.session_state:
        st.session_state["source_mode"] = "bundled_scenarios"
    if "selected_scenario_id" not in st.session_state:
        st.session_state["selected_scenario_id"] = "customer_id_rename"
    if "selected_ai_mode" not in st.session_state:
        try:
            default_settings = load_settings()
            st.session_state["selected_ai_mode"] = (
                default_settings.ai_mode
                if default_settings.ai_mode in {"local", "gemini", "deterministic"}
                else "local"
            )
        except ValueError:
            st.session_state["selected_ai_mode"] = "local"
    if "report_cache" not in st.session_state:
        st.session_state["report_cache"] = {}
    if "active_cache_key" not in st.session_state:
        st.session_state["active_cache_key"] = None
    if "last_error" not in st.session_state:
        st.session_state["last_error"] = None
    if "post_fix_enabled" not in st.session_state:
        st.session_state["post_fix_enabled"] = False

    st.sidebar.markdown("## MergeMesh Controls")
    st.sidebar.caption("Local-Only Runtime (Zero API Credits Required)")

    source_modes = ["bundled_scenarios", "custom_git_repos"]
    source_mode_labels = {
        "bundled_scenarios": "Bundled Example Scenarios",
        "custom_git_repos": "Local Git Repositories (Custom Paths & Refs)",
    }
    selected_source_mode = st.sidebar.radio(
        "Analysis Input Source",
        options=source_modes,
        index=source_modes.index(st.session_state["source_mode"])
        if st.session_state["source_mode"] in source_modes
        else 0,
        format_func=lambda m: source_mode_labels.get(m, m),
    )
    if selected_source_mode != st.session_state["source_mode"]:
        st.session_state["source_mode"] = selected_source_mode
        st.session_state["last_error"] = None
        st.session_state["post_fix_enabled"] = False

    ai_modes = ["local", "gemini", "deterministic"]
    mode_labels = {
        "local": "local — Local Gemma via Ollama + ADK (Auto Fallback)",
        "gemini": "gemini — Hosted Gemma (gemma-4-26b-a4b-it via Gemini API + ADK)",
        "deterministic": "deterministic — Pure Deterministic Engine (No LLM)",
    }
    selected_mode = st.sidebar.selectbox(
        "Execution & Explanation Mode",
        options=ai_modes,
        index=ai_modes.index(st.session_state["selected_ai_mode"])
        if st.session_state["selected_ai_mode"] in ai_modes
        else 0,
        format_func=lambda m: mode_labels.get(m, m),
    )
    st.session_state["selected_ai_mode"] = selected_mode

    settings = load_settings(override_ai_mode=selected_mode)
    readiness = check_provider_readiness(settings, timeout_sec=1.0)

    custom_request: CustomRepoAnalysisRequest | None = None

    if selected_source_mode == "bundled_scenarios":
        scenarios = list_available_scenarios()
        scenario_map = {s.id: s for s in scenarios}
        scenario_ids = list(scenario_map.keys())

        current_sid = st.session_state["selected_scenario_id"]
        if current_sid not in scenario_ids and scenario_ids:
            current_sid = scenario_ids[0]

        selected_sid = st.sidebar.selectbox(
            "Select Change-Set Scenario",
            options=scenario_ids,
            index=scenario_ids.index(current_sid) if current_sid in scenario_ids else 0,
            format_func=lambda sid: scenario_map[sid].title,
        )
        if selected_sid != st.session_state["selected_scenario_id"]:
            st.session_state["selected_scenario_id"] = selected_sid
            st.session_state["post_fix_enabled"] = False
    else:
        st.sidebar.markdown("#### 1. Provider Git Repository")
        prov_path = st.sidebar.text_input(
            "Provider Repo Local Path",
            value=st.session_state.get("custom_prov_path", ""),
            placeholder="e.g., C:/repos/orders-api",
        )
        st.session_state["custom_prov_path"] = prov_path

        p_col1, p_col2 = st.sidebar.columns(2)
        with p_col1:
            prov_base = st.text_input("Base Git Ref", value="HEAD~1", key="custom_prov_base")
        with p_col2:
            prov_target = st.text_input("Proposed Git Ref", value="HEAD", key="custom_prov_target")

        prov_contract = st.sidebar.text_input(
            "Contract File Path (.json or .py, blank = auto-discover)",
            value="",
            placeholder="e.g., contracts/customer.json or api/provider.py",
            key="custom_prov_contract",
        )

        st.sidebar.markdown("#### 2. Consumer Git Repository")
        cons_path = st.sidebar.text_input(
            "Consumer Repo Local Path",
            value=st.session_state.get("custom_cons_path", ""),
            placeholder="e.g., C:/repos/checkout-client",
        )
        st.session_state["custom_cons_path"] = cons_path

        c_col1, c_col2 = st.sidebar.columns(2)
        with c_col1:
            cons_base = st.text_input("Consumer Base Ref (opt)", value="", key="custom_cons_base")
        with c_col2:
            cons_target = st.text_input("Consumer Target Ref", value="HEAD", key="custom_cons_target")

        cons_source = st.sidebar.text_input(
            "Consumer Python File (blank = auto-scan .py files)",
            value="",
            placeholder="e.g., client.py",
            key="custom_cons_source",
        )

        with st.sidebar.expander("3. Optional Pytest Execution (Explicit Approval)"):
            st.caption(
                "Safety Notice: MergeMesh never runs code from user repositories unless you explicitly opt in below. "
                "Subprocesses run locally without container sandboxing."
            )
            approve_tests = st.checkbox(
                "I approve executing the configured pytest files locally",
                value=False,
                key="custom_approve_tests",
            )
            prov_test = st.text_input("Provider Test File (rel .py)", value="", key="custom_prov_test")
            cons_test = st.text_input("Consumer Test File (rel .py)", value="", key="custom_cons_test")
            comb_test = st.text_input("Combined Test File (rel .py)", value="", key="custom_comb_test")
            pf_test = st.text_input("Post-Fix Test File (rel .py)", value="", key="custom_pf_test")

        custom_request = CustomRepoAnalysisRequest(
            provider_repo_path=prov_path,
            consumer_repo_path=cons_path,
            provider_base_ref=prov_base,
            provider_target_ref=prov_target,
            provider_contract_path=prov_contract,
            consumer_base_ref=cons_base,
            consumer_target_ref=cons_target,
            consumer_source_path=cons_source,
            user_approved_test_execution=approve_tests,
            provider_test_rel_path=prov_test,
            consumer_test_rel_path=cons_test,
            combined_test_rel_path=comb_test,
            post_fix_test_rel_path=pf_test,
            run_post_fix=st.session_state["post_fix_enabled"],
        )

    def _trigger_bundled_analysis(run_post_fix: bool = False, force_recompute: bool = False) -> None:
        st.session_state["last_error"] = None
        st.session_state["post_fix_enabled"] = run_post_fix
        try:
            cache_key = compute_analysis_cache_key(
                scenario_id=st.session_state["selected_scenario_id"],
                settings=settings,
                include_ai=(selected_mode != "deterministic"),
                run_post_fix=run_post_fix,
            )
            if force_recompute or cache_key not in st.session_state["report_cache"]:
                with st.spinner("Running local deterministic contract analysis, pytest checks, and ADK workflow..."):
                    report = run_scenario_analysis(
                        scenario_id=st.session_state["selected_scenario_id"],
                        settings=settings,
                        include_ai=(selected_mode != "deterministic"),
                        run_post_fix=run_post_fix,
                    )
                    save_report_artifacts(report)
                    st.session_state["report_cache"][cache_key] = report
            st.session_state["active_cache_key"] = cache_key
        except Exception as exc:
            st.session_state["last_error"] = str(exc)

    def _trigger_custom_analysis(run_post_fix: bool = False) -> None:
        if custom_request is None:
            return
        st.session_state["last_error"] = None
        st.session_state["post_fix_enabled"] = run_post_fix
        custom_request.run_post_fix = run_post_fix
        try:
            raw_key = f"custom|{custom_request}|{settings.ai_mode}|{settings.ollama_model}"
            cache_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:20]
            with st.spinner("Inspecting local Git repositories, comparing contracts, and scanning AST..."):
                report = run_custom_repo_analysis(
                    request=custom_request,
                    settings=settings,
                    include_ai=(selected_mode != "deterministic"),
                )
                save_report_artifacts(report)
                st.session_state["report_cache"][cache_key] = report
                st.session_state["active_cache_key"] = cache_key
        except Exception as exc:
            st.session_state["last_error"] = str(exc)

    if st.sidebar.button("Analyze Change Set", type="primary", use_container_width=True):
        if selected_source_mode == "bundled_scenarios":
            _trigger_bundled_analysis(run_post_fix=False, force_recompute=False)
        else:
            _trigger_custom_analysis(run_post_fix=False)

    if selected_source_mode == "bundled_scenarios" and st.session_state["selected_scenario_id"] == "customer_id_rename":
        if st.sidebar.button("Verify Suggested Fix (Post-Fix Pass)", use_container_width=True):
            _trigger_bundled_analysis(run_post_fix=True, force_recompute=True)
    elif selected_source_mode == "custom_git_repos" and custom_request and custom_request.post_fix_test_rel_path.strip():
        if st.sidebar.button("Verify Suggested Fix (Post-Fix Pass)", use_container_width=True):
            _trigger_custom_analysis(run_post_fix=True)

    if st.sidebar.button("Reset Demo", use_container_width=True):
        st.session_state["report_cache"] = {}
        st.session_state["active_cache_key"] = None
        st.session_state["last_error"] = None
        st.session_state["post_fix_enabled"] = False
        st.session_state["source_mode"] = "bundled_scenarios"
        st.session_state["selected_scenario_id"] = "customer_id_rename"
        st.rerun()

    st.sidebar.divider()
    render_provider_readiness_sidebar(readiness, settings)

    # Auto-run initial default bundled scenario on first load
    if selected_source_mode == "bundled_scenarios":
        if st.session_state["active_cache_key"] is None and st.session_state["last_error"] is None:
            _trigger_bundled_analysis(run_post_fix=False, force_recompute=False)

        expected_key = compute_analysis_cache_key(
            scenario_id=st.session_state["selected_scenario_id"],
            settings=settings,
            include_ai=(selected_mode != "deterministic"),
            run_post_fix=st.session_state["post_fix_enabled"],
        )
        if expected_key in st.session_state["report_cache"]:
            st.session_state["active_cache_key"] = expected_key
        elif st.session_state["active_cache_key"] != expected_key:
            _trigger_bundled_analysis(run_post_fix=st.session_state["post_fix_enabled"], force_recompute=False)

    active_report = st.session_state["report_cache"].get(st.session_state["active_cache_key"])
    run_status = _compute_run_status_label(active_report, st.session_state["last_error"])
    current_input_mode = (
        "local_git_repos"
        if selected_source_mode == "custom_git_repos"
        else "simulated_fixture"
    )

    render_header(
        settings,
        run_status,
        input_mode=current_input_mode,
        ai_status=active_report.ai_explanation.status if active_report else None,
    )

    if st.session_state["last_error"]:
        st.error(f"**Analysis Error:** {st.session_state['last_error']}")
        return

    if active_report is None or (
        selected_source_mode == "custom_git_repos" and active_report.input_mode != "local_git_repos"
    ):
        st.info(
            "Enter local paths to your **Provider Git Repository** and **Consumer Git Repository** in the sidebar, "
            "specify their base and proposed Git revisions, and click **Analyze Change Set**."
        )
        return

    active_scenario = (
        load_scenario_definition(active_report.scenario_id)
        if active_report.input_mode == "simulated_fixture"
        else None
    )

    def _on_apply_fix() -> None:
        if selected_source_mode == "bundled_scenarios":
            _trigger_bundled_analysis(run_post_fix=True, force_recompute=True)
        else:
            _trigger_custom_analysis(run_post_fix=True)
        st.rerun()

    def _on_switch_safe() -> None:
        st.session_state["selected_scenario_id"] = "safe_optional_field"
        st.session_state["post_fix_enabled"] = False
        _trigger_bundled_analysis(run_post_fix=False, force_recompute=False)
        st.rerun()

    def _on_rerun_tests() -> None:
        if selected_source_mode == "bundled_scenarios":
            _trigger_bundled_analysis(run_post_fix=st.session_state["post_fix_enabled"], force_recompute=True)
        else:
            _trigger_custom_analysis(run_post_fix=st.session_state["post_fix_enabled"])
        st.rerun()

    tab_overview, tab_prs, tab_contract, tab_evidence, tab_ai = st.tabs(
        [
            "1. Overview",
            "2. PR Changes (Diffs)",
            "3. Dependency & Contract",
            "4. Test Evidence",
            "5. AI Explanation (ADK)",
        ]
    )

    with tab_overview:
        render_overview_tab(
            report=active_report,
            on_apply_fix=_on_apply_fix,
            on_switch_safe=_on_switch_safe if selected_source_mode == "bundled_scenarios" else None,
        )

    with tab_prs:
        render_pr_changes_tab(report=active_report, scenario=active_scenario)

    with tab_contract:
        render_contract_tab(report=active_report, scenario=active_scenario)

    with tab_evidence:
        render_test_evidence_tab(
            report=active_report,
            on_rerun_tests=_on_rerun_tests,
            on_apply_fix=_on_apply_fix,
        )

    with tab_ai:
        render_ai_explanation_tab(
            report=active_report,
            on_regenerate_ai=_on_rerun_tests,
        )


if __name__ == "__main__":
    main()
