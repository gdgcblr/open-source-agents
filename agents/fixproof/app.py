"""
FixProof — Civic Complaint Discrepancy Assessor (Streamlit Dashboard)
=====================================================================
A clean civic-tech UI for evaluating civic complaints where an authority
marked an issue as resolved or closed but a resident reports the issue persists.

Runs deterministically using the core Python assessment engine without
requiring external LLM or network calls.
"""

from __future__ import annotations

import json
from typing import Any
import streamlit as st

from fixproof_core import assess_complaint

# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

DEMO_DATA: dict[str, str] = {
    "complaint_reference": "CMP-2026-04821",
    "issue_category": "Road Maintenance",
    "location": "MG Road, Ward 12, Bengaluru",
    "original_description": (
        "Large pothole approximately 2 feet wide near bus stop causing traffic hazard."
    ),
    "original_report_date": "2026-06-15",
    "authority_status": "resolved",
    "status_update_date": "2026-07-20",
    "resolution_note": "Pothole filled with cold-mix asphalt.",
    "followup_observation": (
        "The patch has washed away after monsoon rains; the pothole is again "
        "visible and approximately the same size as originally reported."
    ),
    "followup_observation_date": "2026-09-10",
    "evidence_text": (
        "Photo of pothole taken on 2026-09-10 showing exposed aggregate.\n"
        "Measurement showing depth of approximately 6 inches."
    ),
}

# ---------------------------------------------------------------------------
# Data parsing helper
# ---------------------------------------------------------------------------


def prepare_complaint_dict(
    complaint_reference: str,
    issue_category: str,
    location: str,
    original_description: str,
    original_report_date: str,
    authority_status: str,
    status_update_date: str = "",
    resolution_note: str = "",
    followup_observation: str = "",
    followup_observation_date: str = "",
    evidence_text: str = "",
) -> dict[str, Any]:
    """Parse UI form values into a clean complaint dict for assess_complaint."""
    complaint_data: dict[str, Any] = {
        "complaint_reference": complaint_reference.strip(),
        "issue_category": issue_category.strip(),
        "location": location.strip(),
        "original_description": original_description.strip(),
        "original_report_date": original_report_date.strip(),
        "authority_status": authority_status.strip(),
    }

    if status_update_date and status_update_date.strip():
        complaint_data["status_update_date"] = status_update_date.strip()
    if resolution_note and resolution_note.strip():
        complaint_data["resolution_note"] = resolution_note.strip()
    if followup_observation and followup_observation.strip():
        complaint_data["followup_observation"] = followup_observation.strip()
    if followup_observation_date and followup_observation_date.strip():
        complaint_data["followup_observation_date"] = followup_observation_date.strip()

    if evidence_text and evidence_text.strip():
        items = [line.strip() for line in evidence_text.splitlines() if line.strip()]
        if items:
            complaint_data["supporting_evidence"] = items

    return complaint_data


# ---------------------------------------------------------------------------
# Streamlit App
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(
        page_title="FixProof — Civic Complaint Follow-Up",
        page_icon="⚖️",
        layout="wide",
    )

    # Header & Mode Indicator
    col_title, col_mode = st.columns([3, 1])
    with col_title:
        st.title("⚖️ FixProof")
        st.markdown(
            "**Evidence-based civic complaint discrepancy assessor & escalation assistant**"
        )
    with col_mode:
        st.info("🏷️ **Mode**: Deterministic assessment\n*(Offline • Local engine)*")

    # Epistemic notice banner
    st.warning(
        "ℹ️ **Disclaimer & Epistemic Notice**: FixProof assesses user-supplied complaint records "
        "and resident observations to detect discrepancies and draft editable escalation letters. "
        "FixProof **does not independently inspect physical conditions**, verify municipal databases, "
        "or submit complaints on your behalf. All resident observations and evidence descriptions are "
        "classified as unverified."
    )

    # Initialize session state for form fields if not present
    for key, val in DEMO_DATA.items():
        if f"field_{key}" not in st.session_state:
            st.session_state[f"field_{key}"] = ""

    # Controls to populate or clear demo data
    col_btn1, col_btn2, _ = st.columns([1.5, 1.5, 5])
    with col_btn1:
        if st.button("📋 Load Demo (Pothole Complaint)", use_container_width=True):
            for k, v in DEMO_DATA.items():
                st.session_state[f"field_{k}"] = v
            st.rerun()
    with col_btn2:
        if st.button("🧹 Clear Form", use_container_width=True):
            for k in DEMO_DATA.keys():
                st.session_state[f"field_{k}"] = ""
            st.rerun()

    # Main Form & Results Layout
    left_col, right_col = st.columns([1, 1], gap="large")

    with left_col:
        st.subheader("1. Complaint Intake Form")
        st.caption("Fields marked with * are required.")

        with st.form("complaint_form"):
            st.markdown("##### Authority Record (User-Supplied)")
            ref = st.text_input(
                "Complaint Reference *",
                value=st.session_state["field_complaint_reference"],
                placeholder="e.g. CMP-2026-04821",
            )
            cat = st.text_input(
                "Issue Category *",
                value=st.session_state["field_issue_category"],
                placeholder="e.g. Road Maintenance, Street Lighting, Solid Waste",
            )
            loc = st.text_input(
                "Location *",
                value=st.session_state["field_location"],
                placeholder="e.g. MG Road, Ward 12, Bengaluru",
            )
            desc = st.text_area(
                "Original Issue Description *",
                value=st.session_state["field_original_description"],
                placeholder="Describe the problem as originally reported...",
                height=90,
            )
            c1, c2 = st.columns(2)
            with c1:
                rep_date = st.text_input(
                    "Original Report Date (YYYY-MM-DD) *",
                    value=st.session_state["field_original_report_date"],
                    placeholder="YYYY-MM-DD",
                )
            with c2:
                auth_status = st.selectbox(
                    "Authority Status *",
                    options=["resolved", "closed", "in_progress", "open", "pending", "rejected"],
                    index=0 if st.session_state["field_authority_status"] == "resolved" else (
                        1 if st.session_state["field_authority_status"] == "closed" else 0
                    ),
                )

            c3, c4 = st.columns(2)
            with c3:
                upd_date = st.text_input(
                    "Status Update Date (YYYY-MM-DD)",
                    value=st.session_state["field_status_update_date"],
                    placeholder="Optional (YYYY-MM-DD)",
                )
            with c4:
                res_note = st.text_input(
                    "Authority Resolution Note",
                    value=st.session_state["field_resolution_note"],
                    placeholder="Optional authority explanation",
                )

            st.markdown("##### Resident Observation & Evidence (Unverified)")
            c5, _ = st.columns([1, 1])
            with c5:
                obs_date = st.text_input(
                    "Follow-up Observation Date (YYYY-MM-DD)",
                    value=st.session_state["field_followup_observation_date"],
                    placeholder="Optional (YYYY-MM-DD)",
                )
            obs_text = st.text_area(
                "Resident Follow-up Observation",
                value=st.session_state["field_followup_observation"],
                placeholder="State your personal observations on the current condition...",
                height=90,
            )
            evi_text = st.text_area(
                "Supporting Evidence Descriptions (one per line)",
                value=st.session_state["field_evidence_text"],
                placeholder="Photo of pothole with exposed aggregate...\nDepth measurement showing 5 inches...",
                height=80,
            )

            submitted = st.form_submit_button(
                "🔍 Run Assessment", type="primary", use_container_width=True
            )

    with right_col:
        st.subheader("2. Assessment Results")

        if submitted:
            complaint_input = prepare_complaint_dict(
                complaint_reference=ref,
                issue_category=cat,
                location=loc,
                original_description=desc,
                original_report_date=rep_date,
                authority_status=auth_status,
                status_update_date=upd_date,
                resolution_note=res_note,
                followup_observation=obs_text,
                followup_observation_date=obs_date,
                evidence_text=evi_text,
            )

            result = assess_complaint(complaint_input)
            st.session_state["last_assessment"] = result

        if "last_assessment" in st.session_state:
            result = st.session_state["last_assessment"]

            if not result.get("valid"):
                st.error("❌ **Validation Failed**: Please correct the following required fields:")
                for err in result.get("validation_errors", []):
                    st.write(f"- {err}")
            else:
                analysis = result.get("analysis", {})
                timeline = result.get("timeline", [])
                flags = analysis.get("flags", [])
                missing = analysis.get("missing_info", [])
                evidence_notes = analysis.get("evidence_notes", [])
                letter = result.get("escalation_letter")

                # 1. Assessment Summary
                st.markdown("#### 📊 Assessment Summary")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Status Recorded", analysis.get("authority_status_recorded", "-"))
                m2.metric(
                    "Discrepancy",
                    "⚠️ Detected" if flags and any("DISCREPANCY" in f for f in flags) else "None",
                )
                m3.metric(
                    "Follow-up",
                    "Provided" if analysis.get("resident_followup_provided") else "None",
                )
                m4.metric("Evidence Items", len(evidence_notes))

                # 2. Discrepancy Flags & Missing Info
                if flags:
                    st.markdown("#### ⚠️ Discrepancy Flags")
                    for flag in flags:
                        st.warning(f"**{flag}**")
                else:
                    st.success("✅ **No Discrepancies Flagged**: Authority status and resident observations do not conflict.")

                if missing:
                    st.markdown("#### ℹ️ Missing Information")
                    for m in missing:
                        st.info(f"• {m}")

                # 3. Chronological Timeline
                st.markdown("#### ⏱️ Chronological Timeline")
                if timeline:
                    t_rows = []
                    for e in timeline:
                        t_rows.append(
                            {
                                "Date": e.get("date"),
                                "Event": e.get("event"),
                                "Detail": e.get("detail"),
                                "Source Provenance": e.get("source"),
                            }
                        )
                    st.dataframe(t_rows, use_container_width=True)
                else:
                    st.write("No timeline events recorded.")

                # 4. Evidence Classifications
                st.markdown("#### 📁 Supporting Evidence Classifications")
                if evidence_notes:
                    e_rows = []
                    for note in evidence_notes:
                        e_rows.append(
                            {
                                "#": note.get("index") + 1,
                                "Description": note.get("description"),
                                "Classification": note.get("classification"),
                                "Verification Note": note.get("note"),
                            }
                        )
                    st.dataframe(e_rows, use_container_width=True)
                else:
                    st.caption("No supporting evidence descriptions were provided.")

                # 5. Escalation Letter
                st.markdown("#### ✉️ Draft Escalation Letter")
                if letter:
                    st.caption(
                        "Editable draft generated from supplied facts only. "
                        "Please review and edit before sending."
                    )
                    st.text_area(
                        "Escalation Letter Content (Editable)",
                        value=letter,
                        height=280,
                        key="ui_escalation_letter",
                    )
                else:
                    st.info("No escalation letter generated because no resolution discrepancy was flagged.")

                # 6. Downloadable JSON Assessment
                st.markdown("#### 💾 Download Assessment")
                json_str = json.dumps(result, indent=2)
                st.download_button(
                    label="📥 Download Structured Assessment (JSON)",
                    data=json_str,
                    file_name=f"fixproof_assessment_{result.get('timeline', [{}])[0].get('date', 'export')}.json",
                    mime="application/json",
                    use_container_width=True,
                )
        else:
            st.info("👈 Fill out the complaint intake form on the left or click **Load Demo** to view an assessment.")


if __name__ == "__main__":
    main()
