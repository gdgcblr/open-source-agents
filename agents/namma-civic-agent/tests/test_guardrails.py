"""Offline tests for the contact-detail guardrail. No API key needed."""

from types import SimpleNamespace

from google.adk.models.llm_response import LlmResponse
from google.genai import types

from namma_civic_agent.guardrails import (
    NOTE,
    REMOVED,
    _allowed_values,
    block_unverified_contacts,
    redact_unverified_contacts,
)

ALLOWED = _allowed_values()


def redact(text, user_text=""):
    return redact_unverified_contacts(text, ALLOWED, user_text)


def test_known_helplines_are_kept():
    text = "1. Civic helpline: 1533\n2. BESCOM helpline: 1912\nCall 112 now."
    assert redact(text) == (text, 0)


def test_invented_phone_number_is_removed():
    cleaned, count = redact("Call the ward office on 080-2222 1188.")
    assert count == 1 and REMOVED in cleaned and "2222" not in cleaned


def test_invented_short_code_is_removed_only_in_call_context():
    cleaned, count = redact("Dial helpline 1800 for help.")
    assert count == 1 and "1800" not in cleaned
    # Numbers in addresses are not contact details.
    assert redact("Pothole on 100 Feet Road, near house 221.") == (
        "Pothole on 100 Feet Road, near house 221.",
        0,
    )


def test_invented_url_email_and_handle_are_removed():
    cleaned, count = redact(
        "File at https://fake-portal.example/complaint, email help@fake.example or tag @FakeCivicBot"
    )
    assert count == 3
    assert "fake" not in cleaned.lower()


def test_details_the_user_gave_are_kept():
    user = "My number is 98450 12345, I live at 560034"
    text = "Contact: 98450 12345. Pincode 560034."
    assert redact(text, user) == (text, 0)


def test_dates_are_not_treated_as_phone_numbers():
    text = "Reported on 24-10-2026."
    assert redact(text) == (text, 0)


def test_kannada_numerals_of_known_helpline_are_kept():
    text = "ಸಹಾಯವಾಣಿ ಸಂಖ್ಯೆ: ೧೫೩೩"
    assert redact(text) == (text, 0)


def _response(*parts):
    return LlmResponse(content=types.Content(role="model", parts=list(parts)))


def _context(text=""):
    return SimpleNamespace(user_content=types.Content(role="user", parts=[types.Part(text=text)]))


def test_callback_rewrites_response_and_adds_note():
    response = _response(types.Part(text="Call 080-4444 5555 for help."))
    result = block_unverified_contacts(_context("pothole"), response)
    assert result is response
    assert REMOVED in result.content.parts[0].text
    assert result.content.parts[0].text.endswith(NOTE)


def test_callback_leaves_clean_and_tool_call_responses_alone():
    clean = _response(types.Part(text="Civic helpline: 1533"))
    assert block_unverified_contacts(_context(), clean) is None
    call = _response(
        types.Part(function_call=types.FunctionCall(name="find_department", args={"issue_type": "pothole"}))
    )
    assert block_unverified_contacts(_context(), call) is None
