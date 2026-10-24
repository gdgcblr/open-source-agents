"""Validation and conservative checks for untrusted AI output."""

import math
import re


class InvalidInputError(ValueError):
    """Raised when an assessment input is not safe to process."""


class UnsafeAIOutput(ValueError):
    """Raised when a model response fails output guardrails."""


_UNIT_PATTERN = re.compile(r"[\w%./µμ·^ -]{1,24}\Z", re.UNICODE)
_UNSAFE_OUTPUT_PATTERNS = (
    re.compile(r"\b(?:i\s+)?diagnos(?:e|ed|is|ing)\b", re.IGNORECASE),
    re.compile(r"\byou\s+(?:have|likely have|probably have)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:this(?:\s+result)?|the result|your result)\s+(?:proves?|shows?)\s+"
        r"(?:that\s+)?(?:you(?:'re| are)\s+healthy|everything\s+is\s+normal)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:your|the)\s+(?:kidneys?|liver|thyroid|heart|lungs?|pancreas|"
        r"organ)\s+(?:is|are)\s+(?:functioning|working)\s+normally\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:take|start|stop|increase|decrease|double|skip)\s+(?:your\s+)?(?:medication|medicine|dose|prescription|insulin|antibiotic)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:you\s+(?:need|should|must)\s+(?:medical\s+)?treatment|"
        r"(?:start|begin|seek|undergo|pursue)\s+(?:medical\s+)?treatment|"
        r"(?:i|we)\s+recommend\s+(?:medical\s+)?treatment|"
        r"(?:treatment|therapy)\s+(?:is|may be|should be)\s+"
        r"(?:needed|necessary|recommended|started|changed|increased|stopped)|"
        r"(?:prescribe|cure))\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:ignore|disregard)\s+(?:all\s+)?(?:previous|prior|safety)\s+instructions\b", re.IGNORECASE),
)


def validate_assessment_input(test_name, result, unit, lower, upper) -> None:
    from domain.assessment import TESTS

    if not isinstance(test_name, str) or test_name not in TESTS:
        raise InvalidInputError("Please select a supported test.")
    if not all(_is_finite_number(value) for value in (result, lower, upper)):
        raise InvalidInputError("Enter valid finite numbers for the result and reference limits.")
    if any(float(value) < 0 or float(value) > 1e12 for value in (result, lower, upper)):
        raise InvalidInputError("Results and reference limits must be between 0 and 1,000,000,000,000.")
    if lower > upper:
        raise InvalidInputError("The lower limit must be less than or equal to the upper limit.")
    if (
        not isinstance(unit, str)
        or any(ord(character) < 32 or ord(character) == 127 for character in unit)
        or not _UNIT_PATTERN.fullmatch(unit.strip())
    ):
        raise InvalidInputError("Enter a valid unit using up to 24 letters, numbers, or common unit symbols.")


def validate_ai_output(answer: str) -> str:
    if not isinstance(answer, str):
        raise UnsafeAIOutput("The local model returned an invalid response.")
    cleaned = answer.strip()
    if not cleaned or len(cleaned) > 1600:
        raise UnsafeAIOutput("The local model response was empty or too long to display safely.")
    if any(pattern.search(cleaned) for pattern in _UNSAFE_OUTPUT_PATTERNS):
        raise UnsafeAIOutput("The local model response included unsafe medical guidance and was blocked.")
    return cleaned


def _is_finite_number(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False
