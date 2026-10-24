"""Extract structured meeting outcomes from plain-text notes."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def normalize_analysis(payload: Any) -> dict[str, Any]:
    """Validate and normalize the model response before printing it."""
    if not isinstance(payload, dict):
        raise ValueError("The response must be a JSON object.")

    summary = payload.get("summary")
    decisions = payload.get("decisions")
    action_items = payload.get("action_items")
    open_questions = payload.get("open_questions")

    if not isinstance(summary, str):
        raise ValueError("The response must include a string 'summary'.")
    if not isinstance(decisions, list) or not all(
        isinstance(item, str) for item in decisions
    ):
        raise ValueError("'decisions' must be a list of strings.")
    if not isinstance(open_questions, list) or not all(
        isinstance(item, str) for item in open_questions
    ):
        raise ValueError("'open_questions' must be a list of strings.")
    if not isinstance(action_items, list):
        raise ValueError("'action_items' must be a list.")

    normalized_items = []
    for item in action_items:
        if not isinstance(item, dict) or not isinstance(item.get("task"), str):
            raise ValueError("Each action item must include a string 'task'.")

        owner = item.get("owner")
        due_date = item.get("due_date")
        if owner is not None and not isinstance(owner, str):
            raise ValueError("An action item's 'owner' must be a string or null.")
        if due_date is not None and not isinstance(due_date, str):
            raise ValueError("An action item's 'due_date' must be a string or null.")

        normalized_items.append(
            {"task": item["task"], "owner": owner, "due_date": due_date}
        )

    return {
        "summary": summary,
        "decisions": decisions,
        "action_items": normalized_items,
        "open_questions": open_questions,
    }


def build_prompt(notes: str) -> str:
    return f"""Analyze these meeting notes and return only a JSON object with this shape:
{{
  "summary": "Brief summary",
  "decisions": ["Decision made"],
  "action_items": [
    {{"task": "Task to do", "owner": null, "due_date": null}}
  ],
  "open_questions": ["Question not resolved"]
}}

Rules:
- Use only information stated in the notes. Do not invent decisions, owners, or dates.
- Use null for an action item's owner or due_date when the notes do not specify one.
- Use empty arrays when there are no decisions, action items, or open questions.
- Keep the summary concise and preserve names and dates as written.

Meeting notes:
{notes}
"""


def analyze_notes(notes: str, api_key: str, model: str) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=build_prompt(notes),
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    if not response.text:
        raise ValueError("The model returned an empty response.")
    return normalize_analysis(json.loads(response.text))


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
    parser = argparse.ArgumentParser(
        description="Extract a summary, decisions, and action items from meeting notes."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Path to a UTF-8 notes file; use - or omit to read standard input.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        help="Gemini model name (default: GEMINI_MODEL or gemini-2.5-flash).",
    )
    args = parser.parse_args()

    try:
        notes = (
            sys.stdin.read()
            if args.input == "-"
            else Path(args.input).read_text(encoding="utf-8")
        )
        if not notes.strip():
            raise ValueError("Meeting notes are empty.")

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Set GEMINI_API_KEY in your environment or local .env file.")

        result = analyze_notes(notes, api_key, args.model)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Gemini request failed: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())