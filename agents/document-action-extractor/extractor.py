import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


def extract_actions(document_text: str) -> list[dict]:
    """Extract action items from document text using Gemini."""
    if not document_text.strip():
        return []

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise ValueError(
            "GEMINI_API_KEY is missing. Add your key to the local .env file."
        )

    client = genai.Client(api_key=api_key)
    model = os.getenv("MODEL_NAME", "gemini-3.8-flash")

    prompt = f"""
Extract actionable tasks from this document.

Rules:
- Extract only explicitly stated or clearly implied actions.
- Never invent owners, deadlines, or priorities.
- Use "Not specified" for missing information.
- Preserve relative dates exactly as written.
- Include a short supporting evidence quote for each task.
- Return an empty list if there are no action items.

Return a JSON array with these string fields:
task, owner, deadline, priority, evidence.

Document:
---
{document_text}
---
"""

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "owner": {"type": "string"},
                        "deadline": {"type": "string"},
                        "priority": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                    "required": [
                        "task",
                        "owner",
                        "deadline",
                        "priority",
                        "evidence",
                    ],
                },
            },
            temperature=0.1,
        ),
    )

    try:
        actions = json.loads(response.text or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("Gemini returned invalid JSON.") from exc

    if not isinstance(actions, list):
        raise ValueError("Gemini returned an unexpected response.")

    fields = ("task", "owner", "deadline", "priority", "evidence")
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("Gemini returned an invalid action item.")

        for field in fields:
            value = action.get(field, "Not specified")
            if not isinstance(value, str):
                raise ValueError(
                    f"Gemini returned a non-string value for '{field}'."
                )
            action[field] = value

    return actions
