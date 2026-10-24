"""Coach model fallback: a busy Gemini model (429/503/timeout) never fails a turn while another option works."""

from __future__ import annotations

import asyncio

import pytest
from google.adk.models import LlmRequest, LlmResponse
from google.genai import errors, types

from mergewarden.coach import llm


class FakeGemini:
    """Fails with the given HTTP code for the listed models, answers for the rest."""

    def __init__(self, busy: dict[str, list[int]]):
        self.busy = busy
        self.calls: list[str] = []

    async def generate_content_async(self, req, stream=False):
        self.calls.append(req.model)
        codes = self.busy.get(req.model, [])
        if codes:
            raise errors.APIError(codes.pop(0), {"error": {"message": "busy", "status": "UNAVAILABLE"}})
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=f"hi from {req.model}")]))


def run(busy, primary_down=False):
    model = llm.FallbackGemini(model="primary", fallback="lite")
    fake = FakeGemini(busy)
    object.__setattr__(model, "_g", fake)
    llm._STATE["primary_down_until"] = 1e18 if primary_down else 0.0
    req = LlmRequest(model="primary", contents=[], config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="low")))

    async def go():
        return [r async for r in model.generate_content_async(req)]

    try:
        return asyncio.run(go()), fake.calls
    finally:
        llm._STATE["primary_down_until"] = 0.0


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(llm, "RETRY_PAUSE_S", 0)


def text(out):
    return out[0].content.parts[0].text


def test_primary_busy_falls_back():
    out, calls = run({"primary": [504]})
    assert text(out) == "hi from lite" and calls == ["primary", "lite"]


def test_fallback_busy_while_primary_cooling_down_tries_primary():
    # The demo failure: primary in cooldown, lite returns 503 "high demand" -> try primary instead of failing.
    out, calls = run({"lite": [503]}, primary_down=True)
    assert text(out) == "hi from primary" and calls == ["lite", "primary"]


def test_both_busy_then_one_more_try_after_a_pause():
    out, calls = run({"primary": [503], "lite": [503]})
    assert text(out) == "hi from lite" and calls == ["primary", "lite", "lite"]


def test_gives_up_when_everything_stays_busy():
    with pytest.raises(errors.APIError):
        run({"primary": [503], "lite": [503, 503]})


def test_non_retryable_errors_are_not_retried():
    with pytest.raises(errors.APIError):
        run({"primary": [400]})
