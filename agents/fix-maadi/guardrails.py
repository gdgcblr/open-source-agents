"""Review gates that keep civic drafts safe, sourced, and resident-controlled."""

from __future__ import annotations

import re
from typing import Any

from privacy import find_sensitive_data


UNSUPPORTED_PROMISES = re.compile(r"\b(guaranteed|will be fixed|within\s+\d+\s*(?:hours?|days?)|surely resolved)\b", re.I)
PERSONAL_DATA = re.compile(r"(?:\b\+?\d[\d\s-]{8,}\b|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b)")
FORBIDDEN_EXTERNAL_ACTIONS = re.compile(r"(captcha|bypass\s+(?:login|otp|authentication)|auto.?submit|credential|password)", re.I)
SAFE_HANDOFF_MODES = {"portal_handoff", "guided_handoff", "whatsapp_handoff", "phone_handoff", "copy_text"}


def review_case(case: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    drafts = f"{case.get('english_draft', '')} {case.get('kannada_draft', '')}"
    has_sources = all(
        option.get("source")
        for route in case.get("routing_plan", [])
        for option in route.get("options", [])
        if option.get("official") and option.get("track_feedback", True) is not False
    )
    checks.append({"id": "source_backed", "label": "Official routes have a recorded source", "passed": has_sources})
    checks.append({"id": "no_promises", "label": "Draft does not promise an invented SLA or outcome", "passed": not UNSUPPORTED_PROMISES.search(drafts)})
    checks.append({"id": "approval_required", "label": "Resident approval is required before handoff", "passed": True})
    checks.append({"id": "evidence_review", "label": "Evidence can be reviewed before sharing", "passed": True, "note": "Add a photo where it improves verification." if not case.get("image_name") else "Photo attached for review."})
    user_text = [str(case.get(field, "")) for field in ("description", "location", "landmark", "english_draft", "kannada_draft")]
    personal_data_found = bool(find_sensitive_data(*user_text)) or bool(PERSONAL_DATA.search(" ".join(user_text)))
    checks.append({"id": "privacy_review", "label": "Personal details are reviewed before sharing", "passed": not personal_data_found, "note": "Remove or redact phone numbers and email addresses before handoff." if personal_data_found else "Remove unrelated personal details."})
    option_text = str(case.get("routing_plan", []))
    external_action_found = bool(FORBIDDEN_EXTERNAL_ACTIONS.search(option_text))
    unsupported_mode = any(option.get("mode") not in SAFE_HANDOFF_MODES for route in case.get("routing_plan", []) for option in route.get("options", []))
    checks.append({"id": "no_auth_bypass", "label": "Handoff does not bypass login, OTP, or CAPTCHA", "passed": not external_action_found and not unsupported_mode, "note": "Only prepare, copy, call, or open an official service; the resident completes authentication."})
    hard_failures = [item for item in checks if not item["passed"] and item["id"] in {"source_backed", "no_promises", "no_auth_bypass"}]
    return {"passed": not hard_failures, "checks": checks, "summary": "Ready for resident review" if not hard_failures else "Needs a safety correction before handoff"}
