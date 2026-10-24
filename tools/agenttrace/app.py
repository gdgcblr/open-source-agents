"""AgentTrace — AI Agent Failure Investigator.

Streamlit web dashboard for deterministic, offline AI agent trace diagnostics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional
import streamlit as st

from analyzer import analyze_trace

EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"


def load_example(filename: str) -> str:
    """Load an example trace JSON file as a string."""
    filepath = EXAMPLES_DIR / filename
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def main() -> None:
    st.set_page_config(
        page_title="AgentTrace — AI Agent Failure Investigator",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("🔍 AgentTrace — AI Agent Failure Investigator")
    st.markdown(
        "Deterministic, offline analysis for AI agent execution traces. "
        "Detect execution errors, repeated tool loops, timeouts, and missing responses "
        "without external model calls or data transmission."
    )

    # Initialize session state keys
    if "input_json" not in st.session_state:
        st.session_state["input_json"] = ""
    if "last_report" not in st.session_state:
        st.session_state["last_report"] = None
    if "analysis_error" not in st.session_state:
        st.session_state["analysis_error"] = None

    # Sidebar: Quick actions & synthetic demo traces
    with st.sidebar:
        st.header("Synthetic Demos")
        st.caption("All demo traces are synthetic test cases conforming to the AgentTrace schema.")

        if st.button("Load Failed Demo (Synthetic)", use_container_width=True):
            st.session_state["input_json"] = load_example("failed_trace.json")
            st.session_state["last_report"] = None
            st.session_state["analysis_error"] = None
            st.rerun()

        if st.button("Load Clean Demo (Synthetic)", use_container_width=True):
            st.session_state["input_json"] = load_example("clean_trace.json")
            st.session_state["last_report"] = None
            st.session_state["analysis_error"] = None
            st.rerun()

        if st.button("Clear Input", use_container_width=True):
            st.session_state["input_json"] = ""
            st.session_state["last_report"] = None
            st.session_state["analysis_error"] = None
            st.rerun()

        st.divider()
        st.markdown("**About AgentTrace**")
        st.markdown(
            "- **Zero network dependency**: 100% offline analysis.\n"
            "- **Rule-based heuristics**: Objective detection with cited evidence.\n"
            "- **Safe handling**: Input is parsed as untrusted data and never executed."
        )

    # Main input section
    st.subheader("1. Provide Agent Execution Trace")
    input_col1, input_col2 = st.columns([1, 1])

    with input_col1:
        uploaded_file = st.file_uploader(
            "Upload JSON execution trace file (.json)",
            type=["json"],
            help="Upload an execution trace conforming to the AgentTrace schema.",
        )
        if uploaded_file is not None:
            try:
                content = uploaded_file.getvalue().decode("utf-8")
                if content != st.session_state["input_json"]:
                    st.session_state["input_json"] = content
                    st.session_state["last_report"] = None
                    st.session_state["analysis_error"] = None
            except Exception as e:
                st.session_state["analysis_error"] = f"Failed to read uploaded file: {str(e)}"
                st.session_state["last_report"] = None

    with input_col2:
        st.caption("Or paste / modify trace JSON directly:")

    trace_text = st.text_area(
        label="Trace JSON text",
        value=st.session_state["input_json"],
        height=220,
        placeholder='{\n  "name": "My Agent Trace",\n  "complete": true,\n  "events": [\n    {"id": "1", "type": "tool_call", "tool": "search", "input": {"q": "test"}},\n    {"id": "2", "type": "tool_result", "call_id": "1", "output": "found 1 item"}\n  ]\n}',
        label_visibility="collapsed",
    )

    # Sync back manual edits in text area
    if trace_text != st.session_state["input_json"]:
        st.session_state["input_json"] = trace_text
        st.session_state["last_report"] = None
        st.session_state["analysis_error"] = None

    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        analyze_clicked = st.button("🚀 Analyze Trace", type="primary", use_container_width=True)

    if analyze_clicked:
        raw_text = st.session_state["input_json"].strip()
        if not raw_text:
            st.session_state["analysis_error"] = "Please paste or upload a JSON execution trace to analyze."
            st.session_state["last_report"] = None
        else:
            try:
                parsed_json = json.loads(raw_text)
                report = analyze_trace(parsed_json)
                st.session_state["last_report"] = report
                st.session_state["analysis_error"] = None
            except json.JSONDecodeError as err:
                st.session_state["analysis_error"] = f"JSON Syntax Error (line {err.lineno}, column {err.colno}): {err.msg}"
                st.session_state["last_report"] = None
            except ValueError as err:
                st.session_state["analysis_error"] = f"Schema Validation Error: {str(err)}"
                st.session_state["last_report"] = None
            except Exception as err:
                st.session_state["analysis_error"] = f"Unexpected processing error: {str(err)}"
                st.session_state["last_report"] = None

    # Error presentation (clears any stale report)
    if st.session_state["analysis_error"]:
        st.error(f"❌ {st.session_state['analysis_error']}")
        return

    report: Optional[Dict[str, Any]] = st.session_state.get("last_report")
    if not report:
        st.info("👆 Paste or upload an execution trace above, or load a synthetic demo from the sidebar to begin.")
        return

    # Results section
    st.divider()
    st.subheader(f"2. Analysis Results: {report['trace_name']}")

    findings = report.get("findings", [])
    crit_high_count = sum(1 for f in findings if f.get("severity") in ("Critical", "High"))

    # Top metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Trace Name", report.get("trace_name", "Untitled"))
    m2.metric("Events Analyzed", report.get("event_count", 0))
    m3.metric("Total Findings", report.get("finding_count", 0))
    m4.metric("Critical / High Issues", crit_high_count, delta="Issues" if crit_high_count > 0 else "Clean", delta_color="inverse" if crit_high_count > 0 else "normal")

    tab_findings, tab_timeline, tab_export = st.tabs(["📋 Diagnostic Findings", "⏱️ Event Timeline", "💾 Export Report"])

    with tab_findings:
        if not findings:
            st.success("No issues detected.")
        else:
            severity_icons = {
                "Critical": "🚨",
                "High": "⚠️",
                "Medium": "🔔",
                "Info": "ℹ️",
            }
            for idx, finding in enumerate(findings):
                sev = finding.get("severity", "Info")
                icon = severity_icons.get(sev, "•")
                title = finding.get("title", "Finding")
                event_id = finding.get("event_id")
                event_badge = f" [Event ID: `{event_id}`]" if event_id else ""

                header_label = f"{icon} [{sev}] {title}{event_badge}"

                expanded = sev in ("Critical", "High")
                with st.expander(header_label, expanded=expanded):
                    st.markdown("**Evidence:**")
                    st.code(finding.get("evidence", "No evidence recorded"), language=None)
                    st.markdown("**Actionable Recommendation:**")
                    st.info(finding.get("recommendation", "Review agent behavior."))

    with tab_timeline:
        timeline = report.get("timeline", [])
        if not timeline:
            st.write("No events in trace.")
        else:
            st.caption(f"Showing all {len(timeline)} chronological events from the trace:")
            for idx, ev in enumerate(timeline):
                if isinstance(ev, dict):
                    ev_id = ev.get("id", f"idx-{idx}")
                    ev_type = ev.get("type", "unknown")
                    tool = ev.get("tool")
                    tool_desc = f" — Tool: `{tool}`" if tool else ""
                    with st.expander(f"Event #{idx}: `{ev_id}` ({ev_type}){tool_desc}"):
                        st.json(ev)
                else:
                    with st.expander(f"Event #{idx}: (Non-object raw entry)"):
                        st.text(str(ev))

    with tab_export:
        st.markdown("Download the full diagnostic report in structured JSON format:")
        report_json_str = json.dumps(report, indent=2, ensure_ascii=False)
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in report.get("trace_name", "trace")).lower()
        st.download_button(
            label="📥 Download JSON Report",
            data=report_json_str,
            file_name=f"{safe_name}_report.json",
            mime="application/json",
            use_container_width=True,
        )
        st.code(report_json_str[:600] + ("\n... [truncated]" if len(report_json_str) > 600 else ""), language="json")


if __name__ == "__main__":
    main()
