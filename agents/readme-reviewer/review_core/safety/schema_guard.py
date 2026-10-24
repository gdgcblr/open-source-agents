"""Keeps the aggregator's output valid so a weak model cannot crash the review.

ADK raises if an `output_schema` agent answers with anything but valid JSON. That would throw
away checks that were already computed, so this `after_model_callback` repairs the answer:
JSON buried in prose is extracted; anything else is replaced by the deterministic report.
"""

from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import ValidationError

from ..analysis.checks import CRITERIA
from .redaction import contains_credential, response_text
from ..analysis.scoring import CriterionScores, ReviewReport, build_report


def _parse(text: str):
    """A valid ReviewReport from the text, or from the first {...} block inside it; else None."""
    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            return ReviewReport.model_validate_json(candidate)
        except ValidationError:
            continue
    return None


def _fallback(state) -> ReviewReport:
    checks = [c for criterion in CRITERIA for c in state.get(f"checks_{criterion}", [])]
    if checks:
        return build_report(checks)
    return ReviewReport(overall_score=0, criterion_scores=CriterionScores(), failures=[],
                        suggested_fixes=[], verdict="needs_changes")


def ensure_valid_review(callback_context, llm_response):
    """ADK `after_model_callback` for the aggregator: always hand ADK a valid ReviewReport."""
    if getattr(llm_response, "partial", False):
        return None  # streaming chunk; the complete answer is checked when it arrives
    text = response_text(llm_response)
    # An answer containing a credential is never passed on; the deterministic report replaces it.
    report = (None if contains_credential(text) else _parse(text)) or _fallback(callback_context.state)
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=report.model_dump_json())]))
