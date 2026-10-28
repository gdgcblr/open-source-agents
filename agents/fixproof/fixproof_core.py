"""
FixProof Core Assessment Engine
================================
Pure-Python module for analysing civic complaints where a resident reports
that an issue persists despite being marked as resolved by an authority.

Combines deterministic discrepancy logic, statutory Citizen Charter SLA
turnaround analysis, objective Civic Priority Index scoring, and structured
evidence integrity auditing.

Zero mandatory external runtime dependencies (operates 100% on Python stdlib;
optionally exports Pydantic v2 schemas when available).
"""

from __future__ import annotations

import copy
from datetime import datetime
import hashlib
from typing import Any

# Optional Pydantic support without forcing a hard runtime dependency
try:
    from pydantic import BaseModel, Field
    PYDANTIC_AVAILABLE = True
except ImportError:
    BaseModel = object  # type: ignore[misc,assignment]
    Field = lambda *args, **kwargs: None  # type: ignore[assignment]
    PYDANTIC_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants & Civic Charter Standards
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

# Statutory Citizen Charter SLA Turnaround Standards (in calendar days)
# Based on municipal Citizen Charters (e.g., Karnataka Sakala Services Act / BBMP)
STATUTORY_SLAS: dict[str, int] = {
    "road": 2,          # 48 hours for filling potholes / asphalt patch repair
    "pothole": 2,
    "street light": 1,  # 24 hours for street lighting restoration
    "lighting": 1,
    "electrical": 1,
    "solid waste": 1,   # 24 hours for unattended waste clearance
    "garbage": 1,
    "waste": 1,
    "sanitation": 1,
    "water": 1,         # 24 hours for pipeline leaks / contamination
    "sewage": 1,
    "drain": 2,         # 48 hours for drain overflow / desilting
    "footpath": 3,      # 72 hours for pedestrian walkway hazards
}
DEFAULT_SLA_DAYS = 7    # 7 days standard administrative SLA

# Public safety keywords for priority index scoring
SAFETY_KEYWORDS: set[str] = {
    "hazard", "danger", "dangerous", "accident", "fatal", "injury",
    "traffic", "school", "hospital", "children", "elderly", "flood",
    "flooding", "pedestrian", "blind spot", "exposed", "spark", "electric",
    "deep", "collapse", "overflow", "stench", "health", "mosquito"
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_date(value: str, field_name: str) -> datetime:
    """Parse a YYYY-MM-DD string or raise ValueError with context."""
    try:
        return datetime.strptime(value, DATE_FORMAT)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"Invalid date format for '{field_name}': expected YYYY-MM-DD, got {value!r}"
        ) from exc


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _detect_evidence_type(description: str) -> str:
    """Classify the evidence description into a structured modality."""
    desc = description.lower()
    if any(k in desc for k in ("photo", "image", "picture", "snapshot", "camera", "photograph")):
        return "photograph"
    if any(k in desc for k in ("inch", "depth", "width", "meter", "cm", "measure", "dimension", "feet")):
        return "measurement"
    if any(k in desc for k in ("petition", "signature", "residents", "appeal", "rwa", "neighborhood")):
        return "petition"
    if any(k in desc for k in ("receipt", "invoice", "work order", "challan", "document", "fir", "letter")):
        return "document"
    if any(k in desc for k in ("video", "footage", "clip", "recording")):
        return "video"
    return "observation_record"


def _generate_sha256_fingerprint(text: str) -> str:
    """Generate a deterministic 16-character SHA-256 fingerprint for data integrity."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def validate_complaint(data: Any) -> list[str]:
    """Return a list of validation-error messages. Empty list == valid."""
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
# Statutory SLA Engine
# ---------------------------------------------------------------------------


def calculate_sla_status(
    issue_category: str,
    original_report_date: str,
    status_update_date: str = "",
) -> dict:
    """Calculate Citizen Charter turnaround metrics and statutory SLA breach status.

    Parameters
    ----------
    issue_category : str
        The civic domain (e.g. 'Road Maintenance', 'Street Lighting').
    original_report_date : str
        Filing date in YYYY-MM-DD.
    status_update_date : str, optional
        Date the authority recorded status update in YYYY-MM-DD.

    Returns
    -------
    dict
        Dictionary containing statutory SLA days, elapsed days, overdue days,
        breach boolean, and statutory charter reference.
    """
    cat_lower = issue_category.lower().strip()
    statutory_days = DEFAULT_SLA_DAYS
    for key, days in STATUTORY_SLAS.items():
        if key in cat_lower:
            statutory_days = days
            break

    try:
        start_dt = _parse_date(original_report_date, "original_report_date")
    except ValueError:
        return {
            "statutory_sla_days": statutory_days,
            "elapsed_days": None,
            "is_breached": False,
            "overdue_days": 0,
            "charter_reference": "Citizen Charter / Sakala Services Standard",
        }

    if _is_non_empty_string(status_update_date):
        try:
            end_dt = _parse_date(status_update_date, "status_update_date")
            elapsed = max(0, (end_dt - start_dt).days)
        except ValueError:
            elapsed = None
    else:
        elapsed = None

    is_breached = bool(elapsed is not None and elapsed > statutory_days)
    overdue_days = max(0, (elapsed - statutory_days)) if elapsed is not None else 0

    return {
        "statutory_sla_days": statutory_days,
        "elapsed_days": elapsed,
        "is_breached": is_breached,
        "overdue_days": overdue_days,
        "charter_reference": (
            f"Statutory Citizen Charter SLA ({statutory_days} day{'s' if statutory_days > 1 else ''} turnaround target)"
        ),
    }


# ---------------------------------------------------------------------------
# Civic Priority Index Engine (0 - 100)
# ---------------------------------------------------------------------------


def calculate_civic_priority(data: dict, analysis: dict) -> dict:
    """Calculate an objective Civic Priority Index (0 - 100) based on multiple factors:
    discrepancy presence, public safety risk keywords, SLA breach, and evidence weight.
    """
    score = 0
    factors: list[str] = []

    # 1. Discrepancy weight (+35)
    has_discrepancy = any("DISCREPANCY" in f for f in analysis.get("flags", []))
    if has_discrepancy:
        score += 35
        factors.append("Premature resolution discrepancy flagged (+35)")

    # 2. Public safety risk keywords (+10 to +25)
    desc = str(data.get("original_description") or "")
    obs = str(data.get("followup_observation") or "")
    cat = str(data.get("issue_category") or "")
    combined_text = f"{desc} {obs} {cat}".lower()
    matched_safety = [k for k in SAFETY_KEYWORDS if k in combined_text]
    if matched_safety:
        safety_bonus = min(25, 10 + len(matched_safety) * 5)
        score += safety_bonus
        factors.append(f"Public safety risk indicators: {', '.join(matched_safety[:3])} (+{safety_bonus})")

    # 3. SLA Breach (+20)
    sla = analysis.get("sla_analysis", {})
    if sla.get("is_breached"):
        score += 20
        factors.append(f"Citizen Charter SLA breached by {sla.get('overdue_days', 0)} days (+20)")

    # 4. Evidence count (+10 to +20)
    evi_count = len(analysis.get("evidence_notes", []))
    if evi_count > 0:
        evi_score = min(20, 10 + (evi_count - 1) * 5)
        score += evi_score
        factors.append(f"Resident evidence descriptions provided ({evi_count} items) (+{evi_score})")

    score = min(100, max(0, score))

    if score >= 75:
        level = "CRITICAL"
    elif score >= 50:
        level = "HIGH"
    elif score >= 25:
        level = "MEDIUM"
    else:
        level = "STANDARD"

    return {
        "score": score,
        "level": level,
        "factors": factors,
    }


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
    """Detect discrepancies, compute SLA metrics, priority index, and classify evidence."""
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

    # Core discrepancy: resolved/closed but resident says problem persists
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

    # Compute Statutory SLA turnaround metrics
    sla_result = calculate_sla_status(
        issue_category=data.get("issue_category", ""),
        original_report_date=data.get("original_report_date", ""),
        status_update_date=data.get("status_update_date", ""),
    )
    if sla_result.get("is_breached"):
        flags.append(
            f"SLA_DELAY: Recorded resolution turnaround was {sla_result.get('elapsed_days')} days, "
            f"exceeding the Citizen Charter target of {sla_result.get('statutory_sla_days')} days "
            f"({sla_result.get('overdue_days')} days overdue)."
        )

    # Classify evidence items with structured modality and integrity fingerprint
    for idx, item in enumerate(evidence_items):
        if _is_non_empty_string(item):
            clean_item = item.strip()
            evi_type = _detect_evidence_type(clean_item)
            fingerprint = _generate_sha256_fingerprint(clean_item)
            evidence_notes.append(
                {
                    "index": idx,
                    "description": clean_item,
                    "classification": "resident_described_evidence",
                    "evidence_type": evi_type,
                    "hash_digest": fingerprint,
                    "note": (
                        "This evidence description is provided by the resident "
                        "and has not been independently verified."
                    ),
                }
            )

    interim_analysis = {
        "authority_status_recorded": data.get("authority_status", ""),
        "status_recognised": status_known,
        "resident_followup_provided": has_followup,
        "flags": flags,
        "missing_info": missing_info,
        "evidence_notes": evidence_notes,
        "sla_analysis": sla_result,
    }

    # Compute Civic Priority Index
    civic_priority = calculate_civic_priority(data, interim_analysis)
    interim_analysis["civic_priority"] = civic_priority

    return interim_analysis


# ---------------------------------------------------------------------------
# Statutory Right to Information (RTI) Query Drafter
# ---------------------------------------------------------------------------


def generate_statutory_rti_queries(data: dict) -> list[str]:
    """Generate precise queries under Section 6(1) of the Right to Information Act, 2005."""
    ref = data.get("complaint_reference", "[Reference]")
    cat = data.get("issue_category", "Civic Maintenance")
    loc = data.get("location", "[Location]")
    status = data.get("authority_status", "resolved")

    return [
        f"Please provide certified copies of the physical site inspection report and official resolution order based on which complaint reference '{ref}' was recorded as '{status}'.",
        f"Please provide the name, designation, and official contact details of the field officer / inspecting engineer who certified completion of work at '{loc}'.",
        f"Please provide certified copies of the contractor work order, completion certificate, and measurement sheet (M-Book) entries pertaining to '{cat}' at '{loc}' under complaint '{ref}'.",
        f"Please provide the geo-tagged photographs submitted by the department or contractor verifying on-site resolution of complaint '{ref}'.",
        f"If no physical verification was conducted prior to updating status to '{status}', please provide copies of relevant municipal rules or circulars permitting status closure without on-site verification."
    ]


# ---------------------------------------------------------------------------
# Civic Jurisdiction Resolver
# ---------------------------------------------------------------------------


def resolve_civic_jurisdiction(issue_category: str, location: str) -> dict:
    """Resolve civic department, supervisory authority, and escalation officer."""
    cat_lower = issue_category.lower()

    if any(k in cat_lower for k in ("road", "pothole", "tar", "asphalt", "footpath", "sidewalk")):
        dept = "Bruhat Bengaluru Mahanagara Palike (BBMP) — Road Infrastructure Division"
        officer = "Ward Executive Engineer (EE) / Chief Engineer (Road Infrastructure)"
        statutory_body = "Karnataka Municipal Corporations Act, 1976"
    elif any(k in cat_lower for k in ("light", "lamp", "electric", "illumination", "pole")):
        dept = "Bangalore Electricity Supply Company (BESCOM) / BBMP Electrical Wing"
        officer = "Assistant Executive Engineer (AEE - Electrical)"
        statutory_body = "Electricity Act, 2003 / Citizen Service Charter"
    elif any(k in cat_lower for k in ("waste", "garbage", "trash", "dump", "swm", "sanitation")):
        dept = "BBMP Solid Waste Management (SWM) Cell"
        officer = "Junior Health Inspector (JHI) / Assistant Executive Engineer (SWM)"
        statutory_body = "Solid Waste Management Rules, 2016"
    elif any(k in cat_lower for k in ("water", "sewer", "drain", "pipe", "pipeline", "sanitary")):
        dept = "Bangalore Water Supply and Sewerage Board (BWSSB)"
        officer = "Assistant Executive Engineer (Water Maintenance & Sub-division)"
        statutory_body = "BWSSB Act, 1964"
    else:
        dept = "Municipal Grievance Redressal Cell / Ward Committee"
        officer = "Zonal Joint Commissioner / Ward Nodal Officer"
        statutory_body = "Citizen Charter & Sakala Services Act"

    return {
        "department": dept,
        "escalation_officer": officer,
        "governing_framework": statutory_body,
        "location": location,
        "jurisdiction_scope": f"Ward level jurisdiction covering {location}",
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

    # SLA context note if breached
    sla = analysis.get("sla_analysis", {})
    if sla.get("is_breached"):
        lines.append(
            f"Statutory Notice: The turnaround time of {sla.get('elapsed_days')} days exceeds "
            f"the Citizen Charter turnaround guideline of {sla.get('statutory_sla_days')} days."
        )
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
        Structured complaint dictionary. See README for the schema.

    Returns
    -------
    dict
        Structured result containing:
        - ``valid`` (bool): whether input passed validation
        - ``validation_errors`` (list[str]): error messages if invalid
        - ``timeline`` (list[dict]): chronological events
        - ``analysis`` (dict): status assessment, flags, missing info,
          evidence notes, statutory SLA analysis, civic priority index
        - ``escalation_letter`` (str | None): draft letter when a
          discrepancy is detected
        - ``metadata`` (dict): classification legend and audit references
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
        "evidence_type_modalities": [
            "photograph",
            "measurement",
            "petition",
            "document",
            "video",
            "observation_record",
        ],
        "civic_priority_index": {
            "range": "0 - 100",
            "bands": ["STANDARD (0-24)", "MEDIUM (25-49)", "HIGH (50-74)", "CRITICAL (75-100)"],
            "scoring_engine": "Multi-factor heuristic: discrepancy (35), safety (25), SLA breach (20), evidence (20)",
        },
        "disclaimer": (
            "This assessment is generated from user-supplied data. "
            "It does not independently verify physical conditions, "
            "nor does it assert that any authority acted improperly."
        ),
    }
