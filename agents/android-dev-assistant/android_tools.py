
import json
import re
from pathlib import Path

KNOWLEDGE_FILE = (
    Path(__file__).parent
    / "knowledge"
    / "android_errors.json"
)

# Common words that don't help identify a technical error.
STOP_WORDS = {
    "the", "and", "for", "with", "from", "this", "that",
    "error", "failed", "failure", "getting", "please",
    "help", "how", "can", "fix", "what", "why"
}


def normalize_text(text: str) -> set[str]:
    """Convert error text into useful searchable keywords."""
    words = re.findall(r"[a-zA-Z0-9_]+", text.lower())

    return {
        word for word in words
        if len(word) > 2 and word not in STOP_WORDS
    }


def search_android_knowledge(error_message: str) -> dict:
    """
    Search Android troubleshooting knowledge and rank relevant entries.
    User-provided error text is treated only as search data.
    """

    if not isinstance(error_message, str):
        return {"found": False, "message": "Invalid error input."}

    if not error_message.strip():
        return {"found": False, "message": "Please provide an error message."}

    if len(error_message) > 2000:
        return {
            "found": False,
            "message": "Error message is too long. Maximum 2000 characters."
        }

    try:
        with KNOWLEDGE_FILE.open("r", encoding="utf-8") as file:
            entries = json.load(file)

        if not isinstance(entries, list):
            raise ValueError("Knowledge base must contain a list.")

    except (OSError, json.JSONDecodeError, ValueError):
        return {
            "found": False,
            "message": "Knowledge base could not be loaded."
        }

    query_keywords = normalize_text(error_message)

    if not query_keywords:
        return {
            "found": False,
            "message": "Please provide more technical details."
        }

    ranked_matches = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        searchable_text = " ".join([
            str(entry.get("error", "")),
            str(entry.get("category", "")),
            str(entry.get("likely_cause", "")),
            " ".join(entry.get("keywords", [])),
            " ".join(entry.get("aliases", []))
        ])

        entry_keywords = normalize_text(searchable_text)

        if not entry_keywords:
            continue

        matched_keywords = query_keywords & entry_keywords

        # Require at least two meaningful matches.
        if len(matched_keywords) < 2:
            continue

        score = len(matched_keywords) / len(query_keywords)

        ranked_matches.append({
            "entry": entry,
            "score": score,
            "matched_keywords": sorted(matched_keywords)
        })

    if not ranked_matches:
        return {
            "found": False,
            "confidence": "low",
            "message": (
                "No reliable knowledge-base match found. "
                "More investigation is needed."
            )
        }

    ranked_matches.sort(
        key=lambda match: match["score"],
        reverse=True
    )

    best_match = ranked_matches[0]

    # Avoid presenting weak matches as confirmed solutions.
    if best_match["score"] < 0.20:
        return {
            "found": False,
            "confidence": "low",
            "message": (
                "The available keywords are not sufficient "
                "to identify a reliable solution."
            )
        }

    if best_match["score"] >= 0.60:
        confidence = "high"
    elif best_match["score"] >= 0.35:
        confidence = "medium"
    else:
        confidence = "low"

    entry = best_match["entry"]

    return {
        "found": True,
        "category": entry.get("category"),
        "likely_cause": entry.get("likely_cause"),
        "suggested_fixes": entry.get("fix", []),
        "verification": entry.get("verification"),
        "source": entry.get("source"),
        "confidence": confidence,
        "matched_keywords": best_match["matched_keywords"]
    }
