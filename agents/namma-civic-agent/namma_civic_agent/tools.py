"""Tools the civic agent can call.

The LLM handles vision, reasoning and writing. These functions are the
source of truth for facts that must be correct: which authority handles an
issue and how to contact them. They only read local JSON files, so they can
be unit-tested without an API key.
"""

import json
import os
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
SEVERITIES = ("low", "medium", "high", "critical")
DEFAULT_COMPLAINTS_DIR = Path(__file__).parent.parent / "complaints"

UNVERIFIED_WARNING = (
    "This contact detail has not been verified yet. Tell the user to confirm "
    "it on the authority's official website or app before relying on it."
)


@lru_cache(maxsize=None)
def _load(filename: str) -> dict:
    with open(DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


def _issue_types() -> list:
    return _load("issue_types.json")["issue_types"]


def _authorities() -> dict:
    return _load("authorities.json")


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def list_issue_types() -> dict:
    """Lists every civic issue category this assistant supports.

    Call this before classifying a photo or description so the issue is mapped
    to one of the official category ids.

    Returns:
        dict: status and a list of categories, each with id, label, Kannada
        label, visual cues and default severity.
    """
    return {
        "status": "success",
        "issue_types": [
            {
                "id": t["id"],
                "label": t["label"],
                "label_kn": t["label_kn"],
                "visual_cues": t["visual_cues"],
                "default_severity": t["default_severity"],
            }
            for t in _issue_types()
        ],
    }


def find_department(issue_type: str) -> dict:
    """Finds which Bengaluru authority and department handles a civic issue.

    Args:
        issue_type: An issue category id from list_issue_types, e.g. "pothole",
            "garbage" or "electrical_hazard".

    Returns:
        dict: status, the matched issue, authority id and name, department,
        default severity and any routing notes. On failure, an error message
        and the list of valid ids.
    """
    key = _normalise(issue_type)
    issue = next(
        (t for t in _issue_types() if t["id"] == key or _normalise(t["label"]) == key),
        None,
    )
    if issue is None:
        return {
            "status": "error",
            "error_message": f"Unknown issue type '{issue_type}'.",
            "valid_issue_types": [t["id"] for t in _issue_types()],
        }

    authority = _get_authority(issue["authority_id"])
    return {
        "status": "success",
        "issue_type": issue["id"],
        "label": issue["label"],
        "label_kn": issue["label_kn"],
        "authority_id": issue["authority_id"],
        "authority_name": authority["name"] if authority else issue["authority_id"],
        "authority_name_kn": authority.get("name_kn") if authority else None,
        "department": issue["department"],
        "default_severity": issue["default_severity"],
        "notes": issue["notes"],
        "verified": issue["verified"],
    }


def _get_authority(authority_id: str):
    return next(
        (a for a in _authorities()["authorities"] if a["id"] == authority_id),
        None,
    )


def get_filing_channels(authority_id: str) -> dict:
    """Gets the official ways to file and escalate a complaint with an authority.

    Args:
        authority_id: The authority id returned by find_department, e.g.
            "city_corporation", "bescom", "bwssb" or "traffic_police".

    Returns:
        dict: status, authority name, the channels that have a known value
        (each marked verified or not), channels still missing data, the
        escalation path and the emergency number.
    """
    authority = _get_authority(_normalise(authority_id))
    if authority is None:
        return {
            "status": "error",
            "error_message": f"Unknown authority '{authority_id}'.",
            "valid_authority_ids": [a["id"] for a in _authorities()["authorities"]],
        }

    channels = []
    missing = []
    for channel in authority["channels"]:
        if channel["value"] is None:
            missing.append(channel["name"])
            continue
        entry = {
            "type": channel["type"],
            "name": channel["name"],
            "value": channel["value"],
            "verified": channel["verified"],
        }
        if not channel["verified"]:
            entry["warning"] = UNVERIFIED_WARNING
        channels.append(entry)

    emergency = _authorities()["emergency"]
    return {
        "status": "success",
        "authority_id": authority["id"],
        "authority_name": authority["name"],
        "channels": channels,
        "channels_not_yet_available": missing,
        "escalation_path": authority["escalation"],
        "emergency": {
            "value": emergency["value"],
            "use_when": emergency["use_when"],
        },
    }


def save_complaint(
    issue_type: str,
    location: str,
    severity: str,
    complaint_english: str,
    complaint_kannada: str,
) -> dict:
    """Saves the final drafted complaint to a local Markdown file.

    Only call this after the user has confirmed they want a copy saved.

    Args:
        issue_type: The issue category id, e.g. "pothole".
        location: The location as described by the user.
        severity: One of "low", "medium", "high" or "critical".
        complaint_english: The full complaint text in English.
        complaint_kannada: The full complaint text in Kannada.

    Returns:
        dict: status and the path of the saved file, or an error message.
    """
    if severity.strip().lower() not in SEVERITIES:
        return {
            "status": "error",
            "error_message": f"Invalid severity '{severity}'. Use one of: {', '.join(SEVERITIES)}.",
        }
    if not complaint_english.strip():
        return {"status": "error", "error_message": "complaint_english is empty."}

    out_dir = Path(os.getenv("COMPLAINTS_DIR", DEFAULT_COMPLAINTS_DIR))
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"{timestamp}-{_normalise(issue_type) or 'issue'}.md"
    path.write_text(
        f"# Civic complaint: {issue_type}\n\n"
        f"- **Location:** {location}\n"
        f"- **Severity:** {severity}\n"
        f"- **Drafted:** {datetime.now().isoformat(timespec='minutes')}\n\n"
        f"## English\n\n{complaint_english.strip()}\n\n"
        f"## ಕನ್ನಡ\n\n{complaint_kannada.strip()}\n",
        encoding="utf-8",
    )
    return {"status": "success", "saved_to": str(path)}
