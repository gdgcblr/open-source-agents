"""
FixProof Core Assessment Engine
================================
Pure-Python module for analysing civic complaints where a resident reports
that an issue persists despite being marked as resolved by an authority.

This module is intentionally free of any LLM or network dependency so that
it can be tested, audited, and used offline.
"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_FIELDS: list[str] = [
    "complaint_reference",
    "issue_category",
    "location",
    "original_description",
    "original_report_date",
    "authority_status",
]

KNOWN_STATUSES: set[str] = {
    "open",
    "in_progress",
    "resolved",
    "closed",
    "rejected",
    "pending",
}

DATE_FORMAT = "%Y-%m-%d"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_date(value: str, field_name: str) -> datetime:
    """Parse a YYYY-MM-DD string or raise *ValueError* with context."""
    try:
        return datetime.strptime(value, DATE_FORMAT)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"Invalid date format for '{field_name}': expected YYYY-MM-DD, got {value!r}"
        ) from exc


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def validate_complaint(data: Any) -> list[str]:
    """Return a list of validation-error messages.  Empty list == valid."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["Input must be a dictionary."]

    for field in REQUIRED_FIELDS:
        if field not in data or not _is_non_empty_string(data.get(field)):
            errors.append(f"Missing or empty required field: '{field}'.")

    # Validate dates that are present
    for date_field in (
        "original_report_date",
        "status_update_date",
        "followup_observation_date",
    ):
        raw = data.get(date_field)
        if raw is not None and _is_non_empty_string(raw):
            try:
                _parse_date(raw, date_field)
            except ValueError as exc:
                errors.append(str(exc))

    # Optional: evidence should be a list if present
    evidence = data.get("supporting_evidence")
    if evidence is not None and not isinstance(evidence, list):
        errors.append("'supporting_evidence' must be a list of strings if provided.")

    return errors


# ---------------------------------------------------------------------------
# Timeline builder
# ---------------------------------------------------------------------------


def build_timeline(data: dict) -> list[dict]:
    """Build a chronological list of events from the complaint data."""
    events: list[dict] = []

    if _is_non_empty_string(data.get("original_report_date")):
        events.append(
            {
                "date": data["original_report_date"],
                "event": "Complaint filed",
                "detail": data.get("original_description", ""),
                "source": "user_supplied_complaint",
            }
        )

    if _is_non_empty_string(data.get("status_update_date")):
        detail_parts = [f"Status set to: {data.get('authority_status', 'unknown')}"]
        if _is_non_empty_string(data.get("resolution_note")):
            detail_parts.append(f"Note: {data['resolution_note']}")
        events.append(
            {
                "date": data["status_update_date"],
                "event": "Authority status update",
                "detail": "; ".join(detail_parts),
                "source": "user_supplied_status",
            }
        )

    if _is_non_empty_string(data.get("followup_observation_date")):
        events.append(
            {
                "date": data["followup_observation_date"],
                "event": "Resident follow-up observation",
                "detail": data.get("followup_observation", "No details provided."),
                "source": "resident_observation",
            }
        )

    # Sort chronologically (stable)
    events.sort(key=lambda e: e["date"])
    return events


# ---------------------------------------------------------------------------
# Analysis / discrepancy detection
# ---------------------------------------------------------------------------


def _analyse_status(data: dict) -> dict:
    """Detect discrepancies, missing info, and classify evidence."""
    status = data.get("authority_status", "").strip().lower()
    has_followup = _is_non_empty_string(data.get("followup_observation"))
    evidence_items = data.get("supporting_evidence") or []

    flags: list[str] = []
    missing_info: list[str] = []
    evidence_notes: list[dict] = []

    # Status classification
    status_known = status in KNOWN_STATUSES
    if not status_known and _is_non_empty_string(data.get("authority_status")):
        flags.append(
            f"Unrecognised authority status: '{data['authority_status']}'. "
            "Manual review recommended."
        )

    # Core discrepancy: resolved but resident says problem persists
    if status in ("resolved", "closed") and has_followup:
        flags.append(
            "DISCREPANCY: The authority recorded the complaint as "
            f"'{data['authority_status']}', but the resident reports that "
            "the issue persists as of their follow-up observation. "
            "Independent verification is recommended."
        )

    # Missing information checks
    if not _is_non_empty_string(data.get("status_update_date")):
        missing_info.append(
            "No status-update date provided by the authority."
        )
    if not _is_non_empty_string(data.get("resolution_note")):
        missing_info.append(
            "No resolution note or explanation provided by the authority."
        )
    if not has_followup:
        missing_info.append(
            "No follow-up observation from the resident."
        )
    if not evidence_items:
        missing_info.append(
            "No supporting evidence descriptions provided."
        )

    # Classify evidence items
    for idx, item in enumerate(evidence_items):
        if _is_non_empty_string(item):
            evidence_notes.append(
                {
                    "index": idx,
                    "description": item.strip(),
                    "classification": "resident_described_evidence",
                    "note": (
                        "This evidence description is provided by the resident "
                        "and has not been independently verified."
                    ),
                }
            )

    return {
        "authority_status_recorded": data.get("authority_status", ""),
        "status_recognised": status_known,
        "resident_followup_provided": has_followup,
        "flags": flags,
        "missing_info": missing_info,
        "evidence_notes": evidence_notes,
    }


# ---------------------------------------------------------------------------
# Escalation letter generator
# ---------------------------------------------------------------------------


def generate_escalation_letter(data: dict, analysis: dict) -> str | None:
    """
    Generate an editable, factual escalation letter.

    Returns *None* when there is no discrepancy to escalate.
    """
    # Only generate when a discrepancy has been flagged
    has_discrepancy = any("DISCREPANCY" in f for f in analysis.get("flags", []))
    if not has_discrepancy:
        return None

    lines: list[str] = []
    lines.append("ESCALATION LETTER — DRAFT (EDITABLE)")
    lines.append("=" * 50)
    lines.append("")
    lines.append("To: [Authority / Department Name]")
    lines.append(f"Date: [Insert today's date]")
    lines.append("")
    lines.append(f"Subject: Follow-up on complaint {data.get('complaint_reference', '[Reference]')}")
    lines.append(f"Category: {data.get('issue_category', '[Category]')}")
    lines.append(f"Location: {data.get('location', '[Location]')}")
    lines.append("")
    lines.append("Dear Sir/Madam,")
    lines.append("")
    lines.append(
        f"I am writing regarding complaint reference "
        f"{data.get('complaint_reference', '[Reference]')}, originally filed "
        f"on {data.get('original_report_date', '[Date]')}."
    )
    lines.append("")
    lines.append("Original issue description:")
    lines.append(f"  {data.get('original_description', '[Description]')}")
    lines.append("")

    if _is_non_empty_string(data.get("status_update_date")):
        lines.append(
            f"According to records, the complaint status was updated to "
            f"'{data.get('authority_status', 'unknown')}' on "
            f"{data.get('status_update_date', '[Date]')}."
        )
    else:
        lines.append(
            f"The complaint was recorded as "
            f"'{data.get('authority_status', 'unknown')}', though no "
            f"status-update date is available."
        )

    if _is_non_empty_string(data.get("resolution_note")):
        lines.append(f"Resolution note provided: {data['resolution_note']}")
    lines.append("")

    lines.append(
        f"However, upon personal observation on "
        f"{data.get('followup_observation_date', '[Date]')}, I note the "
        f"following:"
    )
    lines.append(f"  {data.get('followup_observation', '[Observation]')}")
    lines.append("")

    evidence_items = data.get("supporting_evidence") or []
    if evidence_items:
        lines.append("Supporting evidence (descriptions provided by the resident):")
        for i, item in enumerate(evidence_items, 1):
            lines.append(f"  {i}. {item}")
        lines.append("")

    lines.append(
        "I respectfully request that this complaint be re-examined and "
        "that the reported issue be verified through an independent "
        "inspection."
    )
    lines.append("")
    lines.append("Yours faithfully,")
    lines.append("[Resident Name]")
    lines.append("[Contact Information]")
    lines.append("")
    lines.append("---")
    lines.append(
        "NOTE: This letter is auto-generated from supplied information. "
        "All facts stated are as reported by the complainant and have "
        "not been independently verified. Please review and edit before "
        "sending."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------


def assess_complaint(data: Any) -> dict:
    """
    Perform a complete assessment of a civic complaint.

    Parameters
    ----------
    data : dict
        Structured complaint dictionary.  See README for the schema.

    Returns
    -------
    dict
        Structured result containing:
        - ``valid`` (bool): whether input passed validation
        - ``validation_errors`` (list[str]): error messages if invalid
        - ``timeline`` (list[dict]): chronological events
        - ``analysis`` (dict): status assessment, flags, missing info,
          evidence notes
        - ``escalation_letter`` (str | None): draft letter when a
          discrepancy is detected
        - ``metadata`` (dict): classification legend
    """
    # ---- Validate ----
    errors = validate_complaint(data)
    if errors:
        return {
            "valid": False,
            "validation_errors": errors,
            "timeline": [],
            "analysis": {},
            "escalation_letter": None,
            "metadata": _metadata(),
        }

    # Make a defensive copy so we never mutate the caller's dict
    complaint = copy.deepcopy(data)

    # ---- Build artefacts ----
    timeline = build_timeline(complaint)
    analysis = _analyse_status(complaint)
    letter = generate_escalation_letter(complaint, analysis)

    return {
        "valid": True,
        "validation_errors": [],
        "timeline": timeline,
        "analysis": analysis,
        "escalation_letter": letter,
        "metadata": _metadata(),
    }


def _metadata() -> dict:
    """Return a classification legend so consumers know what labels mean."""
    return {
        "source_classifications": {
            "user_supplied_complaint": (
                "Original complaint details as provided by the user; "
                "not independently verified against official records."
            ),
            "user_supplied_status": (
                "Authority status and resolution notes as reported by the user; "
                "not independently verified against official records."
            ),
            "resident_observation": (
                "Follow-up observation reported by the resident; "
                "not independently verified."
            ),
            "resident_described_evidence": (
                "Supporting evidence description provided by the resident; "
                "not independently verified."
            ),
        },
        "disclaimer": (
            "This assessment is generated from user-supplied data. "
            "It does not independently verify physical conditions, "
            "nor does it assert that any authority acted improperly."
        ),
    }
