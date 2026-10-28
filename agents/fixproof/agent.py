"""
FixProof — Google ADK Agent
============================
Wraps the core assessment engine and civic intelligence tools as Google ADK
tools so that a language model can analyse civic complaints conversationally.

Features a multi-tool agent architecture:
1. analyse_civic_complaint: Core discrepancy, timeline, and escalation analysis.
2. calculate_municipal_sla: Statutory Citizen Charter turnaround compliance.
3. draft_statutory_rti_query: Formal Right to Information (RTI) queries under Sec 6(1).
4. resolve_civic_jurisdiction: Municipal department and escalation authority resolver.

Usage:
    adk run agents/fixproof

Configuration:
    Set GOOGLE_GENAI_USE_VERTEXAI and GOOGLE_API_KEY (or equivalent)
    in a .env file. See .env.example for details.

The core engine (fixproof_core) works completely offline without any
model credentials.
"""

from __future__ import annotations

import os
import sys

# Ensure the package directory is importable when ADK loads agent.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from google.adk.agents import Agent

from fixproof_core import (
    assess_complaint,
    calculate_sla_status,
    generate_statutory_rti_queries,
    resolve_civic_jurisdiction,
)

# ---------------------------------------------------------------------------
# Load environment variables from .env if present
# ---------------------------------------------------------------------------
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ---------------------------------------------------------------------------
# Tools exposed to the ADK agent
# ---------------------------------------------------------------------------


def analyse_civic_complaint(
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
    supporting_evidence: list[str] | str | None = None,
) -> dict:
    """Analyse a civic complaint for discrepancies between authority status
    and resident observations.

    Call this tool as soon as the user supplies the required complaint fields.
    Accepts structured complaint fields and returns a full assessment
    including a chronological timeline, discrepancy flags, missing-information
    notes, evidence classifications, statutory SLA analysis, priority scoring,
    and an optional draft escalation letter.

    Args:
        complaint_reference: Official complaint or ticket reference number.
        issue_category: Category of the issue (e.g. "Road Maintenance").
        location: Location where the issue was reported.
        original_description: Original description of the problem.
        original_report_date: Date the complaint was filed (YYYY-MM-DD).
        authority_status: Status recorded by the authority (e.g. "resolved", "closed", "in_progress").
        status_update_date: Date the authority updated the status (YYYY-MM-DD). Optional.
        resolution_note: Note provided by the authority explaining resolution. Optional.
        followup_observation: Resident's follow-up observation text. Optional.
        followup_observation_date: Date of the follow-up observation (YYYY-MM-DD). Optional.
        supporting_evidence: List of evidence description strings (or single string). Optional.

    Returns:
        A dictionary with keys: valid, validation_errors, timeline, analysis,
        escalation_letter, and metadata.
    """
    complaint_data: dict = {
        "complaint_reference": str(complaint_reference).strip() if complaint_reference else "",
        "issue_category": str(issue_category).strip() if issue_category else "",
        "location": str(location).strip() if location else "",
        "original_description": str(original_description).strip() if original_description else "",
        "original_report_date": str(original_report_date).strip() if original_report_date else "",
        "authority_status": str(authority_status).strip() if authority_status else "",
    }

    # Only add optional fields if they are non-empty
    if status_update_date and str(status_update_date).strip():
        complaint_data["status_update_date"] = str(status_update_date).strip()
    if resolution_note and str(resolution_note).strip():
        complaint_data["resolution_note"] = str(resolution_note).strip()
    if followup_observation and str(followup_observation).strip():
        complaint_data["followup_observation"] = str(followup_observation).strip()
    if followup_observation_date and str(followup_observation_date).strip():
        complaint_data["followup_observation_date"] = str(followup_observation_date).strip()

    # Normalize supporting_evidence to list of strings
    if supporting_evidence is not None:
        if isinstance(supporting_evidence, str):
            evidence_clean = [supporting_evidence.strip()] if supporting_evidence.strip() else []
        elif isinstance(supporting_evidence, list):
            evidence_clean = [str(item).strip() for item in supporting_evidence if str(item).strip()]
        else:
            evidence_clean = []
        if evidence_clean:
            complaint_data["supporting_evidence"] = evidence_clean

    return assess_complaint(complaint_data)


def calculate_municipal_sla(
    issue_category: str,
    original_report_date: str,
    status_update_date: str = "",
) -> dict:
    """Calculate Citizen Charter turnaround metrics, statutory SLA deadlines,
    and overdue duration for a civic complaint.

    Args:
        issue_category: Category of civic issue (e.g. "Road Maintenance", "Street Lighting").
        original_report_date: Date complaint was filed (YYYY-MM-DD).
        status_update_date: Date status was updated by authority (YYYY-MM-DD). Optional.

    Returns:
        Dictionary with statutory_sla_days, elapsed_days, is_breached, overdue_days,
        and charter_reference.
    """
    return calculate_sla_status(
        issue_category=str(issue_category).strip(),
        original_report_date=str(original_report_date).strip(),
        status_update_date=str(status_update_date).strip() if status_update_date else "",
    )


def draft_statutory_rti_query(
    complaint_reference: str,
    issue_category: str,
    location: str,
    authority_status: str,
) -> dict:
    """Generate precision queries under Section 6(1) of the Right to Information Act, 2005
    pertaining to physical inspection reports, contractor work orders, and resolution records.

    Args:
        complaint_reference: Official ticket or grievance number.
        issue_category: Category of the complaint.
        location: Location of the reported issue.
        authority_status: Status recorded by the authority.

    Returns:
        Dictionary with structured RTI queries and statutory instructions.
    """
    data = {
        "complaint_reference": str(complaint_reference).strip(),
        "issue_category": str(issue_category).strip(),
        "location": str(location).strip(),
        "authority_status": str(authority_status).strip(),
    }
    queries = generate_statutory_rti_queries(data)
    return {
        "complaint_reference": data["complaint_reference"],
        "statutory_act": "Right to Information Act, 2005 (Section 6(1))",
        "queries": queries,
        "submission_guidance": (
            "Submit to the Public Information Officer (PIO) of the concerned municipal corporation. "
            "Enclose statutory fee (e.g., Rs. 10 postal order or court fee stamp)."
        ),
    }


def resolve_civic_jurisdiction_tool(
    issue_category: str,
    location: str,
) -> dict:
    """Identify the responsible municipal department, supervisory escalation authority,
    and governing legal act for a civic issue in Bengaluru.

    Args:
        issue_category: Category of civic issue (e.g. "Road Maintenance", "Solid Waste").
        location: Locality or ward name.

    Returns:
        Dictionary detailing primary department, escalation officer, and governing framework.
    """
    return resolve_civic_jurisdiction(
        issue_category=str(issue_category).strip(),
        location=str(location).strip(),
    )


# ---------------------------------------------------------------------------
# ADK Agent definition
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "gemini-3.5-flash-lite"
MODEL_NAME = os.environ.get("FIXPROOF_MODEL", DEFAULT_MODEL)

AGENT_INSTRUCTION = (
    "You are FixProof, an evidence-based civic complaint follow-up agent. "
    "You help residents document and escalate civic complaints where an authority "
    "marked an issue as resolved or closed but the resident reports the problem persists.\n\n"
    "OPERATING INSTRUCTIONS:\n\n"
    "1. DIRECT TOOL INVOCATION (DO NOT ASK FOR SUPPLIED DATA):\n"
    "   - When the user provides complaint information (in text, JSON, key-value pairs, or table), "
    "extract all supplied fields immediately.\n"
    "   - Required fields: complaint_reference, issue_category, location, original_description, "
    "original_report_date (YYYY-MM-DD), authority_status.\n"
    "   - Optional fields: status_update_date, resolution_note, followup_observation, "
    "followup_observation_date, supporting_evidence.\n"
    "   - If ALL 6 required fields are present in the user's input, IMMEDIATELY call "
    "`analyse_civic_complaint`. DO NOT ask the user to confirm, repeat, or provide fields they have already supplied.\n"
    "   - DO NOT delay the tool call to ask for optional fields. If optional fields are absent, "
    "invoke the tool directly; the tool automatically identifies and notes missing optional information.\n\n"
    "2. INCOMPLETE INPUT HANDLING:\n"
    "   - ONLY if one or more of the 6 REQUIRED fields are genuinely absent from the user's input, "
    "ask specifically and concisely for ONLY the missing required fields.\n"
    "   - Never ask the user to re-enter information they already gave you.\n\n"
    "3. CONSOLIDATED SINGLE-RESPONSE OUTPUT:\n"
    "   - After `analyse_civic_complaint` executes, synthesize the tool output into ONE concise, "
    "consolidated response. Do not produce multiple piecemeal responses or repeat conversational pleasantries.\n"
    "   - Organize your response using the following structured markdown sections:\n"
    "     * ### Assessment Summary: Concise overview of complaint validity, recorded authority status, "
    "resident follow-up status, discrepancy status, and Civic Priority Index score.\n"
    "     * ### Chronological Timeline: Chronological sequence of events showing date, event description, "
    "and source label (`user_supplied_complaint`, `user_supplied_status`, or `resident_observation`).\n"
    "     * ### Discrepancy Flags: Explicitly list any flags identified by the tool, or state 'No discrepancies detected.'\n"
    "     * ### Missing Information: Explicitly list any missing information noted by the tool, or state 'None.'\n"
    "     * ### Source & Evidence Classifications: Note the classification legend and list supporting evidence descriptions "
    "as `resident_described_evidence` (unverified) with evidence modality type.\n"
    "     * ### Escalation Letter: If `escalation_letter` is generated in the tool output, display the full editable draft text "
    "and remind the resident to review and edit it before submission. If no letter was generated (e.g. no discrepancy), "
    "state that no escalation letter is warranted.\n\n"
    "4. EPISTEMIC HONESTY & OBJECTIVITY:\n"
    "   - Strictly use supplied facts. Never invent dates, official responses, or evidence.\n"
    "   - Clearly label all resident observations and user-supplied data as unverified by FixProof.\n"
    "   - Discrepancies warrant human/independent review; never claim authority misconduct, fraud, or proven facts.\n\n"
    "5. CIVIC ESCALATION & RTI GUIDANCE:\n"
    "   - If the user specifically inquires about statutory turnaround or Citizen Charter deadlines, "
    "call `calculate_municipal_sla` to provide statutory SLA timelines.\n"
    "   - If the user asks for legal or RTI drafting assistance, call `draft_statutory_rti_query`.\n"
    "   - If the user asks which civic authority or officer to approach, call `resolve_civic_jurisdiction_tool`."
)

root_agent = Agent(
    name="fixproof",
    model=MODEL_NAME,
    description=(
        "FixProof: an evidence-based civic complaint follow-up agent. "
        "Analyses complaints where an authority has marked an issue as "
        "resolved but a resident reports the problem persists. Builds "
        "timelines, flags discrepancies, calculates statutory SLA breaches, "
        "scores civic priority, and drafts factual escalation letters."
    ),
    instruction=AGENT_INSTRUCTION,
    tools=[
        analyse_civic_complaint,
        calculate_municipal_sla,
        draft_statutory_rti_query,
        resolve_civic_jurisdiction_tool,
    ],
)
