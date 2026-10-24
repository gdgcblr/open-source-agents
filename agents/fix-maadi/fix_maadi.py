"""Fix Maadi: a dependency-free civic casefile agent and local web demo."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from guardrails import review_case
from privacy import find_sensitive_data
from vision import infer_image


ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
CASE_FILE = DATA_DIR / "cases.json"


def _load_local_env() -> None:
    """Load simple KEY=VALUE entries from the ignored project-local .env."""
    env_file = ROOT / ".env"
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_local_env()

_channel_file = os.environ.get("FIX_MAADI_CHANNEL_FILE", "data/bengaluru_channels.json")
CHANNEL_FILE = Path(_channel_file)
if not CHANNEL_FILE.is_absolute():
    CHANNEL_FILE = ROOT / CHANNEL_FILE


def _load_channels() -> dict[str, Any]:
    """Load the contribution-friendly channel registry, with a safe fallback."""
    try:
        registry = json.loads(CHANNEL_FILE.read_text(encoding="utf-8"))
        return registry.get("categories", {})
    except (FileNotFoundError, json.JSONDecodeError, AttributeError):
        return {}

RULES = [
    {
        "category": "Pothole / road damage",
        "keywords": ("pothole", "crater", "road damage", "damaged road", "asphalt", "broken road", "speed breaker"),
        "authority": "Suggested: ward roads / civic engineering team",
        "channel": "Namma Bengaluru (Sahaaya 2.0) or the current ward grievance channel",
        "evidence": ("wide shot showing the road context", "close shot showing depth or scale", "nearest landmark"),
        "kn": "ರಸ್ತೆಯ ಗುಂಡಿ ಅಥವಾ ರಸ್ತೆ ಹಾನಿಯ ಕುರಿತು ದೂರು",
    },
    {
        "category": "Waterlogging / drainage",
        "keywords": ("waterlogging", "water logged", "flood", "drain", "stagnant water", "overflow", "rainwater", "water", "rain"),
        "authority": "Suggested: ward drainage / storm-water team; verify whether BWSSB is involved",
        "channel": "Namma Bengaluru (Sahaaya 2.0) or the relevant drainage grievance channel",
        "evidence": ("photo showing the water level and road", "time and rainfall context", "nearest drain or landmark"),
        "kn": "ನೀರು ನಿಲ್ಲುವಿಕೆ ಅಥವಾ ಚರಂಡಿ ಸಮಸ್ಯೆಯ ಕುರಿತು ದೂರು",
    },
    {
        "category": "Garbage / waste",
        "keywords": ("garbage", "waste", "dump", "trash", "litter", "not collected", "smell"),
        "authority": "Suggested: ward solid-waste management team",
        "channel": "Swachha Bengaluru or Namma Bengaluru (Sahaaya 2.0)",
        "evidence": ("photo showing the full dumping spot", "how long it has remained", "nearest landmark"),
        "kn": "ಕಸ ವಿಲೇವಾರಿ ಅಥವಾ ಕಸ ಸಂಗ್ರಹ ಸಮಸ್ಯೆಯ ಕುರಿತು ದೂರು",
    },
    {
        "category": "Streetlight / visibility",
        "keywords": ("streetlight", "street light", "lamp", "dark", "light not working", "darkness"),
        "authority": "Suggested: ward electrical / streetlight maintenance team",
        "channel": "Namma Bengaluru (Sahaaya 2.0) streetlight grievance route",
        "evidence": ("night photo from a safe position", "pole number if visible", "nearest landmark"),
        "kn": "ಬೀದಿ ದೀಪದ ಸಮಸ್ಯೆಯ ಕುರಿತು ದೂರು",
    },
    {
        "category": "Footpath / accessibility",
        "keywords": ("footpath", "sidewalk", "pavement", "blocked", "wheelchair", "encroachment", "walking"),
        "authority": "Suggested: ward roads / public-realm team",
        "channel": "Namma Bengaluru (Sahaaya 2.0) or the current ward grievance channel",
        "evidence": ("photo showing the obstruction and safe walking width", "accessibility impact", "nearest landmark"),
        "kn": "ಪಾದಚಾರಿ ದಾರಿ ಅಥವಾ ಪ್ರವೇಶಾರ್ಹತೆಯ ಸಮಸ್ಯೆಯ ಕುರಿತು ದೂರು",
    },
]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _pick_rule(text: str) -> tuple[dict[str, Any], int]:
    normalized = text.lower()
    ranked = []
    for rule in RULES:
        matched = [keyword for keyword in rule["keywords"] if keyword in normalized]
        weighted_score = sum(len(keyword) for keyword in matched)
        ranked.append((weighted_score, len(matched), rule))
    weighted_score, match_count, rule = max(ranked, key=lambda item: (item[0], item[1]))
    return (rule if weighted_score else {
        "category": "General civic issue",
        "authority": "Suggested: confirm the ward and responsible civic department",
        "channel": "Namma Bengaluru (Sahaaya 2.0) or the relevant government grievance channel",
        "evidence": ("clear photo", "nearest landmark", "date and time observed"),
        "kn": "ಸಾರ್ವಜನಿಕ ನಾಗರಿಕ ಸಮಸ್ಯೆಯ ಕುರಿತು ದೂರು",
    }, match_count)


def _severity(text: str, category: str) -> tuple[str, str]:
    lower = text.lower()
    critical_words = ("injury", "accident", "fell", "electric", "live wire", "open manhole", "child", "fire")
    high_words = ("dangerous", "deep", "blind", "night", "blocked", "urgent", "bike", "water-filled")
    if any(word in lower for word in critical_words):
        return "critical", "Immediate safety risk may be present; avoid the hazard and use emergency services if someone is in danger."
    if any(word in lower for word in high_words) or category in {"Streetlight / visibility", "Waterlogging / drainage"}:
        return "high", "The issue may create a safety or access risk; capture evidence from a safe position."
    return "moderate", "A clear location and dated evidence will make the report easier to act on."


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]{3,}", value.lower()) if token not in {"the", "and", "near"}}


def _duplicate(category: str, location: str, landmark: str, coordinates: dict[str, Any], existing: Any) -> dict[str, Any] | None:
    if not isinstance(existing, list):
        return None
    latitude = _clean(coordinates.get("latitude")) if isinstance(coordinates, dict) else ""
    longitude = _clean(coordinates.get("longitude")) if isinstance(coordinates, dict) else ""
    if not latitude or not longitude:
        return None
    for item in existing:
        if not isinstance(item, dict):
            continue
        if item.get("category") != category:
            continue
        candidate_coordinates = item.get("coordinates") or {}
        if (_clean(candidate_coordinates.get("latitude")) == latitude
                and _clean(candidate_coordinates.get("longitude")) == longitude):
            return item
    return None


def _rank_options(category: str, description: str, options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark the best-fit route using transparent issue-specific rules."""
    ranked = [dict(option) for option in options]
    preferred_id = ""
    reason = ""
    lower = description.lower()
    if category == "Garbage / waste":
        if any(term in lower for term in ("dumping", "dumped", "vacant", "roadside", "burning")):
            preferred_id = "bbmp-waste-whatsapp"
            reason = "Best fit because the description concerns illegal dumping evidence, the scope published for this WhatsApp channel."
        elif any(term in lower for term in ("not collected", "missed collection", "collection", "pickup")):
            preferred_id = "bbmp-waste-helpline"
            reason = "Best fit because this sounds like a waste-service or collection complaint rather than illegal-dumping evidence."
    if not preferred_id:
        preferred = next((item for item in ranked if item.get("mode") == "portal_handoff"), None)
        preferred_id = _clean(preferred.get("id")) if preferred else ""
        reason = "Best general-purpose fit among the currently verified options."
    for option in ranked:
        option["recommended"] = bool(preferred_id and option.get("id") == preferred_id)
        if option["recommended"]:
            option["recommendation_reason"] = reason
    return sorted(ranked, key=lambda item: not item.get("recommended", False))


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    description = _clean(payload.get("description"))
    location = _clean(payload.get("location"))
    landmark = _clean(payload.get("landmark"))
    observed_at = _clean(payload.get("observed_at"))
    duration = _clean(payload.get("duration"))
    image_name = _clean(payload.get("image_name"))
    pole_number = _clean(payload.get("pole_number"))
    coordinates = payload.get("coordinates") if isinstance(payload.get("coordinates"), dict) else {}
    image_inference = infer_image(_clean(payload.get("image_data")), image_name and _clean(payload.get("image_mime")) or "image/jpeg", description)
    if image_inference:
        description = image_inference["description"]
    combined = " ".join(part for part in (description, location, landmark) if part)
    rule, confidence_hits = _pick_rule(combined)
    if image_inference and image_inference.get("category") in {item["category"] for item in RULES}:
        rule = next(item for item in RULES if item["category"] == image_inference["category"])
        confidence_hits = max(confidence_hits, 2)
    category = rule["category"]
    detected_issues = [
        candidate["category"]
        for candidate in RULES
        if any(keyword in combined.lower() for keyword in candidate["keywords"])
    ]
    severity, safety_note = _severity(combined, category)
    questions = []
    if not location and not landmark:
        questions.append({"field": "location", "label": "Where exactly is it?", "hint": "a map pin, street, or nearest landmark", "required": True})
    if not observed_at:
        questions.append({"field": "observed_at", "label": "When did you observe it?", "hint": "Approximate date and time is enough", "required": True})
    if not description:
        questions.append({"field": "description", "label": "What happened?", "hint": "Describe the issue and who it affects", "required": True})
    if category == "Garbage / waste" and not duration:
        questions.append({"field": "duration", "label": "How long has this continued?", "hint": "For example: four days", "required": True})
    if category == "Streetlight / visibility" and not pole_number:
        questions.append({"field": "pole_number", "label": "Is a pole number visible?", "hint": "Optional — say 'not visible' if there is none", "required": False})
    missing = [question["hint"] for question in questions if question["required"]]
    case_key = "|".join((category, location, landmark, description)).lower().encode()
    case_id = "FM-" + hashlib.sha256(case_key).hexdigest()[:8].upper()
    duplicate = _duplicate(category, location, landmark, coordinates, payload.get("existing_cases"))
    confirmed_location = location or landmark or "Location still needs confirmation"
    english = (
        f"Subject: {category} near {confirmed_location}\n\n"
        f"I am reporting a {category.lower()} observed near {confirmed_location}. "
        f"{description or 'Please inspect and address this public issue.'} "
        f"It was observed at {observed_at or '[date and time to be added]'}. "
        "Please acknowledge the complaint, share the responsible team, and update the resolution status."
    )
    kannada = (
        f"ವಿಷಯ: {confirmed_location} ಬಳಿ {rule['kn']}\n\n"
        f"{confirmed_location} ಬಳಿ ಸಾರ್ವಜನಿಕ ಸಮಸ್ಯೆ ಕಂಡುಬಂದಿದೆ. "
        "ದಯವಿಟ್ಟು ಸ್ಥಳ ಪರಿಶೀಲಿಸಿ, ಸಂಬಂಧಿಸಿದ ತಂಡಕ್ಕೆ ಕಳುಹಿಸಿ ಮತ್ತು ಪರಿಹಾರದ ಸ್ಥಿತಿಯನ್ನು ತಿಳಿಸಿ."
    )
    channels = _load_channels()
    route_categories = [category] + [item for item in detected_issues if item != category]
    routing_plan = []
    for route_category in route_categories:
        route_rule = next((item for item in RULES if item["category"] == route_category), rule)
        route_entry = channels.get(route_category, {})
        route_options = _rank_options(route_category, description, route_entry.get("options", []))
        routing_plan.append({
            "category": route_category,
            "authority": route_entry.get("authority", route_rule["authority"]),
            "reason": route_entry.get("reason", "This team commonly handles this type of civic issue."),
            "options": route_options,
        })
    status = "needs_information" if missing else "ready_for_review"
    decision_trace = [
        {"stage": "observe", "summary": "Read the resident description, place context, time, and optional coordinates."},
        {"stage": "classify", "summary": f"Selected {category} with {('high' if confidence_hits >= 2 else 'medium' if confidence_hits == 1 else 'low')} confidence."},
        {"stage": "decompose", "summary": f"Preserved {len([item for item in detected_issues if item != category])} related issue(s) instead of collapsing them."},
        {"stage": "clarify", "summary": "Asked for required missing fields." if missing else "Required context is present."},
        {"stage": "route", "summary": f"Prepared {len(routing_plan)} issue-specific routing plan(s) from the local channel registry."},
        {"stage": "approval_gate", "summary": "Resident approval is required before any external channel is opened or used."},
    ]
    result = {
        "case_id": case_id,
        "category": category,
        "related_categories": [item for item in detected_issues if item != category],
        "confidence": "high" if confidence_hits >= 2 else "medium" if confidence_hits == 1 else "low",
        "severity": severity,
        "safety_note": safety_note,
        "location": confirmed_location,
        "missing_confirmation": missing,
        "questions": questions,
        "suggested_authority": rule["authority"],
        "suggested_channel": rule["channel"],
        "evidence_checklist": list(rule["evidence"]),
        "english_draft": english,
        "kannada_draft": kannada,
        "duplicate_candidate": duplicate,
        "follow_up": [
            "Save the case ID and submission receipt.",
            "Check the official channel later and record any status update.",
            "If the issue is marked resolved, verify it in person before closing your case.",
        ],
        "privacy_note": "Remove faces, vehicle plates, and unrelated personal details before sharing evidence.",
        "privacy_findings": find_sensitive_data(description, location, landmark),
        "status": status,
        "image_name": image_name,
        "vision_provider": image_inference.get("provider", "local") if image_inference else "local",
        "routing_plan": routing_plan,
        "decision_trace": decision_trace,
        "submission_options": routing_plan[0]["options"] if routing_plan else [],
        "submission_note": "Fix Maadi prepares and hands off the case. Review it before using any official channel.",
        "duration": duration,
        "pole_number": pole_number,
        "coordinates": coordinates,
    }
    result["guardrails"] = review_case(result)
    return result


def _read_cases() -> list[dict[str, Any]]:
    try:
        return json.loads(CASE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _write_case(case: dict[str, Any]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    cases = [item for item in _read_cases() if item.get("case_id") != case.get("case_id")]
    cases.append(case)
    CASE_FILE.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")


def channel_stats() -> dict[str, dict[str, int]]:
    """Aggregate transparent, local-only channel feedback without inventing a score."""
    stats: dict[str, dict[str, int]] = {}
    for case in _read_cases():
        feedback = case.get("channel_feedback")
        if not isinstance(feedback, dict) or not feedback.get("channel_id"):
            continue
        category = _clean(feedback.get("category")) or "Unknown"
        key = f"{category}::{feedback['channel_id']}"
        item = stats.setdefault(key, {"reports": 0, "accepted": 0, "resolved": 0})
        item["reports"] += 1
        item["accepted"] += int(feedback.get("accepted") is True)
        item["resolved"] += int(feedback.get("resolved") is True)
    return stats


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/cases":
            self._send(200, json.dumps(_read_cases(), ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        if path == "/api/channels":
            self._send(200, json.dumps(_load_channels(), ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        if path == "/api/channel-stats":
            self._send(200, json.dumps(channel_stats(), ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        static_files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        }
        if path not in static_files:
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        filename, content_type = static_files[path]
        body = (ROOT / "static" / filename).read_bytes()
        self._send(200, body, content_type)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            payload = payload if isinstance(payload, dict) else {}
            if path == "/api/analyze":
                result = analyze(payload)
            elif path == "/api/cases":
                payload["existing_cases"] = _read_cases()
                result = analyze(payload)
                if result.get("duplicate_candidate"):
                    result = result["duplicate_candidate"]
                    result["status"] = "existing"
                    self._send(200, json.dumps(result, ensure_ascii=False).encode(), "application/json; charset=utf-8")
                    return
                _write_case(result)
            elif path.startswith("/api/cases/") and path.endswith("/approve"):
                case_id = path.split("/")[3]
                cases = _read_cases()
                result = next((item for item in cases if item.get("case_id") == case_id), None)
                if result is None:
                    self._send(404, b"Case not found", "text/plain; charset=utf-8")
                    return
                result["status"] = "approved"
                result["approved_submission_mode"] = payload.get("mode", "guided_handoff")
                result["approved_channel_id"] = _clean(payload.get("channel_id"))
                result["approved_channel_name"] = _clean(payload.get("channel_name"))
                if _clean(payload.get("english_draft")):
                    result["english_draft"] = _clean(payload["english_draft"])
                if _clean(payload.get("kannada_draft")):
                    result["kannada_draft"] = _clean(payload["kannada_draft"])
                _write_case(result)
            elif path.startswith("/api/cases/") and path.endswith("/feedback"):
                case_id = path.split("/")[3]
                cases = _read_cases()
                result = next((item for item in cases if item.get("case_id") == case_id), None)
                if result is None:
                    self._send(404, b"Case not found", "text/plain; charset=utf-8")
                    return
                result["channel_feedback"] = {
                    "channel_id": _clean(payload.get("channel_id")),
                    "category": _clean(payload.get("category")) or result.get("category", "Unknown"),
                    "accepted": payload.get("accepted") is True,
                    "resolved": payload.get("resolved") is True,
                    "scope": "local_demo",
                }
                _write_case(result)
            else:
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
            self._send(200, json.dumps(result, ensure_ascii=False).encode(), "application/json; charset=utf-8")
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, json.dumps({"error": str(exc)}).encode(), "application/json; charset=utf-8")

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Fix Maadi civic casefile demo.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Fix Maadi running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
