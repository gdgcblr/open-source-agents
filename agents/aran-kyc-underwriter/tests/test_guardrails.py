"""Offline guardrail tests: no Gemini key, no Ollama, no network."""

from types import SimpleNamespace

import pytest
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types

import aran
from aran import audit
from kyc_underwriter.guardrails import Guardrails
from run import parse_report

PAN = "BQKPR4821M"


@pytest.fixture
def g(tmp_path, monkeypatch):
    monkeypatch.setenv("ARAN_HOME", str(tmp_path))
    r = aran.redact_text(f"PAN card holder PAN {PAN}", "kyc", use_llm=False)  # seeds the vault
    return Guardrails(r.session_id)


def request(*parts: types.Part, role: str = "user") -> LlmRequest:
    return LlmRequest(contents=[types.Content(role=role, parts=list(parts))])


def test_g1_user_input_is_masked_before_sending(g):
    req = request(types.Part(text=f"applicant PAN is {PAN}, call +91 90000 41275"))
    assert g.before_model(None, req) is None  # masked, so allowed through
    assert req.contents[0].parts[0].text == "applicant PAN is <PAN_1>, call <PHONE_1>"


def test_g2_raw_value_in_tool_result_blocks_the_request(g):
    leaky = types.Part(function_response=types.FunctionResponse(
        name="redact_document", response={"text": f"Account holder PAN {PAN}"}))
    resp = g.before_model(None, request(leaky))
    assert isinstance(resp, LlmResponse)
    assert "egress blocked" in resp.content.parts[0].text and PAN not in resp.content.parts[0].text
    events = audit.read(g.session_id, events=True)
    assert events[-1]["event"] == "egress blocked" and events[-1]["types"] == ["PAN"]


def test_g2_redacted_tool_result_passes(g):
    ok = types.Part(function_response=types.FunctionResponse(
        name="redact_document", response={"text": "Account holder PAN <PAN_1>, IFSC HDFC0001234"}))
    assert g.before_model(None, request(ok)) is None


def test_g3_tool_allowlist_and_profile_lock(g):
    assert g.before_tool(SimpleNamespace(name="delete_files"), {}, None)["error"]
    assert g.before_tool(SimpleNamespace(name="redact_document"), {"doc_id": "doc_1", "profile": "health"}, None)["error"]
    assert g.before_tool(SimpleNamespace(name="redact_document"), {"doc_id": "doc_1", "profile": "kyc"}, None) is None


def test_g4_model_output_with_real_value_is_replaced(g):
    out = LlmResponse(content=types.Content(role="model", parts=[types.Part(text=f"The PAN is {PAN}")]))
    blocked = g.after_model(None, out)
    assert blocked is not None and PAN not in blocked.content.parts[0].text


def test_g6_non_eligible_verdict_always_requires_review():
    text = '```json\n{"verdict": "DECLINE", "requires_human_review": false}\n```'
    assert parse_report(text)["requires_human_review"] is True
    assert parse_report('{"verdict": "APPROVE_NOW"}') is None
