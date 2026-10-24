"""Optional Gemini vision provider with a deterministic, offline fallback boundary."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any


SUPPORTED_CATEGORIES = {
    "Pothole / road damage",
    "Waterlogging / drainage",
    "Garbage / waste",
    "Streetlight / visibility",
    "Footpath / accessibility",
    "General civic issue",
}


def _json_from_text(value: str) -> dict[str, Any] | None:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", value.strip(), flags=re.IGNORECASE)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def infer_image(image_data: str, mime_type: str, context: str = "") -> dict[str, Any] | None:
    """Infer a civic issue from inline image bytes when Gemini is configured.

    Returns None for absent configuration, malformed responses, network errors,
    or an over-sized image so callers can safely use the local rule engine.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or not image_data or len(image_data) > 12_000_000:
        return None
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    prompt = (
        "You are a civic issue classifier for Bengaluru. Inspect the image and return ONLY valid JSON with keys "
        "description, category, confidence, safety_flags. category must be exactly one of: "
        "Pothole / road damage; Waterlogging / drainage; Garbage / waste; Streetlight / visibility; "
        "Footpath / accessibility; General civic issue. Do not invent an address, ward, authority, SLA, or person. "
        f"Resident context: {context or 'none provided'}."
    )
    body = json.dumps({"contents": [{"parts": [
        {"text": prompt},
        {"inline_data": {"mime_type": mime_type or "image/jpeg", "data": image_data}},
    ]}]}).encode("utf-8")
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
        parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = next((part.get("text") for part in parts if isinstance(part, dict) and part.get("text")), "")
        result = _json_from_text(text)
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError):
        return None
    if not result or result.get("category") not in SUPPORTED_CATEGORIES or not result.get("description"):
        return None
    return {
        "description": str(result["description"]).strip()[:1000],
        "category": result["category"],
        "confidence": result.get("confidence", "medium"),
        "safety_flags": result.get("safety_flags", []),
        "provider": "gemini",
    }
