"""Quota handling without calling Gemini: the parent Gemini call is replaced by a fake."""

import asyncio

import pytest
from google.adk.models import Gemini

from invoice_chaser import agent as agent_mod
from invoice_chaser.agent import QuotaAwareGemini, classify_rate_limit

DAILY = ("429 RESOURCE_EXHAUSTED ... quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier' "
         "Please retry in 21h27m38.5s.")
MINUTE = ("429 RESOURCE_EXHAUSTED ... quotaId': 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier' "
          "Please retry in 3.2s.")


def test_classify():
    assert classify_rate_limit(RuntimeError(DAILY)) == ("daily", None)
    assert classify_rate_limit(RuntimeError(MINUTE)) == ("minute", 3.2)
    assert classify_rate_limit(RuntimeError("500 INTERNAL")) == (None, None)
    wrapped = ValueError("node failed")
    wrapped.__cause__ = RuntimeError(DAILY)
    assert classify_rate_limit(wrapped)[0] == "daily"


def collect(model):
    async def go():
        return [r async for r in model.generate_content_async(llm_request=None)]
    return asyncio.run(go())


def fake_parent(monkeypatch, errors):
    calls = {"n": 0}

    async def fake(self, llm_request, stream=False):
        calls["n"] += 1
        if errors:
            raise RuntimeError(errors.pop(0))
        from google.adk.models.llm_response import LlmResponse
        from google.genai import types
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part.from_text(text="ok")]))

    monkeypatch.setattr(Gemini, "generate_content_async", fake)
    return calls


def test_daily_quota_returns_message_immediately(monkeypatch):
    calls = fake_parent(monkeypatch, [DAILY])
    responses = collect(QuotaAwareGemini(model="gemini-test"))
    assert calls["n"] == 1  # no retries
    assert responses[0].error_code == "DAILY_QUOTA_EXHAUSTED"
    text = responses[0].content.parts[0].text
    assert "daily free-tier quota" in text and "21h 27m" in text and "--replay" in text


def test_minute_limit_waits_then_succeeds(monkeypatch):
    slept = []

    async def no_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(agent_mod.asyncio, "sleep", no_sleep)
    calls = fake_parent(monkeypatch, [MINUTE, MINUTE])
    responses = collect(QuotaAwareGemini(model="gemini-test"))
    assert calls["n"] == 3 and slept == [4.2, 4.2]
    assert responses[0].content.parts[0].text == "ok"


def test_other_errors_propagate(monkeypatch):
    fake_parent(monkeypatch, ["400 INVALID_ARGUMENT API key not valid"])
    with pytest.raises(RuntimeError):
        collect(QuotaAwareGemini(model="gemini-test"))
