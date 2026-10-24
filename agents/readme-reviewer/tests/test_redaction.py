from types import SimpleNamespace

import pytest
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from review_core.safety.redaction import (
    BLOCKED_MESSAGE,
    REDACTED,
    block_secret_output,
    contains_credential,
    find_credentials,
    redact,
    redact_model_input,
    redact_value,
)
from review_core.safety.schema_guard import ensure_valid_review
from review_core.analysis.tools import scan_for_secrets

# Built from parts so this file never contains a literal key for the scanner to flag.
GOOGLE = "AIza" + "A" * 35
NVIDIA = "nvapi-" + "b" * 30
OPENAI = "sk-" + "c" * 30
GITHUB = "ghp_" + "d" * 36
AWS = "AKIA" + "E" * 16
SECRETS = [GOOGLE, NVIDIA, OPENAI, GITHUB, AWS]


@pytest.mark.parametrize("secret", SECRETS)
def test_each_credential_type_is_redacted(secret):
    assert redact(f"my key is {secret} ok") == f"my key is {REDACTED} ok"
    assert contains_credential(secret)


def test_private_key_header_and_quoted_assignment_are_redacted():
    assert contains_credential("-----" + "BEGIN RSA PRIVATE KEY" + "-----")
    assert redact("api_key = " + '"' + "abcd1234" * 3 + '"') == REDACTED


def test_ordinary_text_and_placeholders_are_untouched():
    for text in ("Add your API key to .env", 'api_key = "your_api_key_goes_here_ok"',
                 "GOOGLE_API_KEY=your_google_api_key_here", "sk-short", "plain README text"):
        assert redact(text) == text and not contains_credential(text)


def test_find_credentials_names_the_type():
    assert find_credentials(f"x {NVIDIA}") == ["NVIDIA API key"]


def test_redact_value_handles_nesting():
    value = {"a": [f"k {GOOGLE}", {"b": (OPENAI, 5)}], "n": None}
    assert redact_value(value) == {"a": [f"k {REDACTED}", {"b": (REDACTED, 5)}], "n": None}


# ---- before_model_callback -------------------------------------------------- #
def request_with(*parts):
    return LlmRequest(contents=[types.Content(role="user", parts=list(parts))])


def test_user_message_and_tool_results_are_redacted_before_the_model():
    request = request_with(
        types.Part(text=f"Review it, my key is {GOOGLE}"),
        types.Part(function_response=types.FunctionResponse(
            name="read_file", response={"content": f"token {NVIDIA}", "n": 1})),
    )
    assert redact_model_input(None, request) is None  # None = continue to the model
    text_part, tool_part = request.contents[0].parts
    assert GOOGLE not in text_part.text and REDACTED in text_part.text
    assert tool_part.function_response.response == {"content": f"token {REDACTED}", "n": 1}


def test_request_without_secrets_is_unchanged():
    request = request_with(types.Part(text="Review template"))
    redact_model_input(None, request)
    assert request.contents[0].parts[0].text == "Review template"


# ---- after_model_callback --------------------------------------------------- #
def response(text, partial=False):
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]), partial=partial)


def test_output_with_a_credential_is_blocked():
    result = block_secret_output(None, response(f"The key is {GOOGLE}"))
    assert result.content.parts[0].text == BLOCKED_MESSAGE


def test_streaming_chunk_with_a_credential_is_blocked_too():
    assert block_secret_output(None, response(GITHUB, partial=True)) is not None


def test_clean_output_passes_through():
    assert block_secret_output(None, response("All good.")) is None


def test_aggregator_output_with_a_credential_is_replaced_by_the_deterministic_report():
    leaky = ('{"overall_score": 99, "criterion_scores": {}, "failures": [], '
             f'"suggested_fixes": ["use {OPENAI}"], "verdict": "ready"}}')
    state = {"checks_security": [{"id": "no_secrets", "criterion": "security", "passed": False,
                                  "applicable": True, "reason": "leak"}]}
    out = ensure_valid_review(SimpleNamespace(state=state), response(leaky)).content.parts[0].text
    assert OPENAI not in out and '"overall_score":0' in out


# ---- scanner shares the patterns -------------------------------------------- #
def test_scanner_ignores_placeholders_but_finds_real_keys(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "ok.py").write_text('api_key = "your_api_key_goes_here_ok"\n')
    assert scan_for_secrets(str(proj))["clean"]
    (proj / "bad.py").write_text(f'KEY = "{GITHUB}"\n')
    result = scan_for_secrets(str(proj))
    assert [f["file"] for f in result["findings"]] == ["bad.py"] and GITHUB not in str(result)


# ---- wiring ----------------------------------------------------------------- #
def test_every_llm_agent_has_both_guardrails():
    from readme_reviewer.agent import root_agent as simple
    from readme_reviewer_team.agent import aggregator, reviewers

    for agent in [simple, aggregator, *reviewers.sub_agents]:
        assert agent.before_model_callback is redact_model_input, agent.name
        assert agent.after_model_callback is not None, agent.name
    for agent in [simple, *reviewers.sub_agents]:
        assert agent.after_model_callback is block_secret_output, agent.name
    assert aggregator.after_model_callback is ensure_valid_review
