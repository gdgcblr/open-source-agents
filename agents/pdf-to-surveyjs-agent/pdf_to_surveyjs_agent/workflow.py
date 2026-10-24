"""Bounded PDF-to-SurveyJS conversion workflow built on Google ADK."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.adk.agents.run_config import RunConfig
from google.genai import types

from .agent import build_agent, configured_model_name
from .schemas import ConversionResult
from .tools import extract_pdf, normalize_survey, validate_survey

MAX_MODEL_TEXT_CHARACTERS = 100_000
MAX_REPAIR_ATTEMPTS = 2


class ConfigurationError(RuntimeError):
    """Raised when model credentials or model settings are unavailable."""


class ConversionError(RuntimeError):
    """Raised when extraction or bounded model conversion fails."""


def _require_configuration() -> str:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key or api_key.strip().lower().startswith(("your_", "replace_")):
        raise ConfigurationError(
            "Gemma execution is not configured. Set GOOGLE_API_KEY (or "
            "GEMINI_API_KEY) to a real key in .env. No fallback model was used."
        )
    return configured_model_name()


def _parse_model_json(text: str) -> dict[str, Any]:
    """Find and validate the required JSON envelope in a model response.

    ADK's output schema should normally make the whole response valid JSON. The
    scanning fallback tolerates a model adding a short preface or Markdown fence
    without accepting arbitrary partial structures.
    """

    candidate = text.strip()
    fenced = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.DOTALL | re.IGNORECASE
    )
    if fenced:
        candidate = fenced.group(1).strip()

    parsed_objects: list[Any] = []
    try:
        parsed_objects.append(json.loads(candidate))
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", candidate):
            try:
                value, _ = decoder.raw_decode(candidate[match.start() :])
            except json.JSONDecodeError:
                continue
            parsed_objects.append(value)

    for value in parsed_objects:
        if isinstance(value, dict) and set(value) == {"survey", "warnings"}:
            return _validate_model_envelope(value)

    raise ConversionError(
        "Model response did not contain the required SurveyJS JSON object."
    )


def _validate_model_envelope(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConversionError("Model response must be a JSON object.")
    if set(value) != {"survey", "warnings"}:
        raise ConversionError(
            "Model response must contain exactly the keys 'survey' and 'warnings'."
        )
    if not isinstance(value["survey"], dict):
        raise ConversionError("Model response 'survey' must be an object.")
    if not isinstance(value["warnings"], list) or not all(
        isinstance(item, str) for item in value["warnings"]
    ):
        raise ConversionError("Model response 'warnings' must be an array of strings.")
    return value


def _friendly_model_error(exc: Exception) -> ConversionError:
    message = str(exc)
    if "RESOURCE_EXHAUSTED" in message or "429" in message:
        return ConversionError(
            "Gemma quota was exceeded. Wait for the quota window to reset, use a "
            "smaller PDF, or use an account with a higher quota."
        )
    if "PERMISSION_DENIED" in message or "403" in message:
        return ConversionError(
            "Gemma access was denied. Check the API key and model access in Google AI Studio."
        )
    if "UNAUTHENTICATED" in message or "401" in message:
        return ConversionError("The Google API key was rejected.")
    if "NOT_FOUND" in message or "404" in message:
        return ConversionError(
            "The configured Gemma model was not found or is unavailable to this account."
        )
    return ConversionError(f"Gemma request failed: {type(exc).__name__}.")


async def _run_turn(
    runner: InMemoryRunner, session_id: str, prompt: str
) -> str:
    chunks: list[str] = []
    try:
        async for event in runner.run_async(
            user_id="local-user",
            session_id=session_id,
            new_message=types.Content(
                role="user", parts=[types.Part.from_text(text=prompt)]
            ),
            run_config=RunConfig(max_llm_calls=3),
        ):
            if getattr(event, "error_code", None):
                raise _friendly_model_error(
                    RuntimeError(
                        getattr(event, "error_message", None)
                        or f"Gemma request failed with {event.error_code}."
                    )
                )
            if not event.content or not event.content.parts:
                continue
            event_text = "".join(
                part.text or ""
                for part in event.content.parts
                if not getattr(part, "thought", False)
            )
            if event_text:
                chunks.append(event_text)
    except ConversionError:
        raise
    except Exception as exc:
        raise _friendly_model_error(exc) from exc
    if not chunks:
        raise ConversionError("The model returned no final text response.")
    return chunks[-1]


async def convert_pdf(
    pdf_path: str | Path, *, max_retries: int = 1
) -> ConversionResult:
    """Extract a PDF, request a draft, validate it, and retry repairs boundedly."""

    if not 0 <= max_retries <= MAX_REPAIR_ATTEMPTS:
        raise ValueError(f"max_retries must be between 0 and {MAX_REPAIR_ATTEMPTS}.")

    extraction = extract_pdf(pdf_path)
    if not extraction.ok:
        raise ConversionError(extraction.error or "PDF extraction failed.")
    if extraction.character_count < 20:
        warning = extraction.warnings[0] if extraction.warnings else "No useful text found."
        raise ConversionError(warning)

    model_name = _require_configuration()
    source_text = extraction.text
    workflow_warnings = list(extraction.warnings)
    if len(source_text) > MAX_MODEL_TEXT_CHARACTERS:
        source_text = source_text[:MAX_MODEL_TEXT_CHARACTERS]
        workflow_warnings.append(
            f"Extracted text was truncated to {MAX_MODEL_TEXT_CHARACTERS} characters."
        )

    app = App(name="pdf_to_surveyjs", root_agent=build_agent(model_name))
    runner = InMemoryRunner(app=app)
    session_id = f"conversion-{uuid.uuid4().hex}"
    await runner.session_service.create_session(
        app_name=app.name, user_id="local-user", session_id=session_id
    )

    prompt = f"""
Create a complete SurveyJS form definition containing ALL questions from ALL {extraction.page_count} pages of the document text below.
CRITICAL INSTRUCTIONS:
- You must extract questions from Page 1, Page 2, Page 3, and every subsequent page until the end. DO NOT stop after Page 1.
- In "elements", EVERY single item MUST be a JSON object (dictionary) with "type", "name", and "title". NEVER return strings or bare text inside "elements".
  Example element: {{"type": "text", "name": "applicant_name", "title": "Applicant Name", "isRequired": true}}
- For "html" questions, you MUST provide the "html" string property:
  {{"type": "html", "name": "notice", "html": "<p>Instructions here</p>"}}
- Set the top-level form "title" and "description" from the document header.
- Create separate "pages" for each major section (e.g. "Tell us about you", "Contact details", "Experience in care", "Family details").
- Use verbatim question labels from the form.
- Use inputType "date" for date fields, "email" for emails, "tel" for phones, and type "comment" for multi-line text.
- Do not use ${{question}} in visibleIf expressions. Use {{question}} = 'value'.
- Return only the required JSON wrapper with "survey" and "warnings".

<untrusted_pdf_text>
{source_text}
</untrusted_pdf_text>
""".strip()

    last_errors: list[str] = []
    attempts = max_retries + 1
    for attempt in range(1, attempts + 1):
        try:
            response = await _run_turn(runner, session_id, prompt)
            parsed = _parse_model_json(response)
            normalized_survey, normalization_warnings = normalize_survey(
                parsed["survey"]
            )
            validation = validate_survey(normalized_survey)
            if validation.valid:
                warnings = (
                    workflow_warnings
                    + parsed["warnings"]
                    + normalization_warnings
                    + validation.warnings
                )
                return ConversionResult(
                    survey=normalized_survey,
                    warnings=list(dict.fromkeys(warnings)),
                    model=model_name,
                    attempts=attempt,
                )
            last_errors = validation.errors
        except ConversionError as exc:
            last_errors = [str(exc)]

        if attempt <= max_retries:
            prompt = (
                "Repair your previous JSON response. Return the complete wrapper again and "
                "change only what is needed to fix these deterministic validation errors:\n- "
                + "\n- ".join(last_errors)
            )

    raise ConversionError(
        f"Model output remained invalid after {attempts} attempt(s): "
        + "; ".join(last_errors)
    )

