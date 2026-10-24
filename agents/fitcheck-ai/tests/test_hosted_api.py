"""Hosted-Gemma (Gemini API) path — tested offline with a fake genai client.

The real ADK `Gemini` / `Gemma` classes build the request; only the network
call is faked. This verifies what would actually be sent to the API.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from google.adk.agents import LlmAgent  # noqa: E402
from google.adk.models.google_llm import Gemini  # noqa: E402
from google.adk.models.lite_llm import LiteLlm  # noqa: E402
from google.adk.models.llm_request import LlmRequest  # noqa: E402
from google.genai import types  # noqa: E402

from fitcheck_ai import models  # noqa: E402
from test_fitcheck import CANNED, _img_data_url  # noqa: E402


# --- model factory ---------------------------------------------------------

def test_default_model_follows_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert models.default_model() == models.LOCAL_DEFAULT
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert models.default_model() == models.HOSTED_DEFAULT


def test_factory_picks_right_adk_class(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    g4 = models.build_model("gemma-4-26b-a4b-it")
    g3 = models.build_model("gemma-3-27b-it")
    local = models.build_model("ollama_chat/gemma3:4b")
    assert isinstance(g4, Gemini) and g4.retry_options.attempts >= 3
    assert 429 in g4.retry_options.http_status_codes
    assert isinstance(g3, models._SafeGemma3)
    assert isinstance(local, LiteLlm)


@pytest.mark.asyncio
async def test_gemma3_keeps_instructions_even_without_user_content(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    req = LlmRequest(model="gemma-3-27b-it", contents=[],
                     config=types.GenerateContentConfig(system_instruction="STYLE RULES"))
    await models.build_model("gemma-3-27b-it")._preprocess_request(req)
    texts = [p.text for c in req.contents for p in c.parts]
    assert "STYLE RULES" in texts and req.config.system_instruction is None


def test_thinking_only_for_gemma4(monkeypatch):
    monkeypatch.setenv("FITCHECK_THINKING", "minimal")
    assert models.generation_config("gemma-4-31b-it", 0.5).thinking_config.thinking_level is not None
    assert models.generation_config("gemma-3-27b-it", 0.5).thinking_config is None
    assert models.generation_config("ollama_chat/gemma3:4b", 0.5).thinking_config is None


# --- full pipeline against a fake Gemini API -------------------------------

class FakeGenAI:
    """Mimics google.genai.Client just enough for ADK's Gemini class."""

    def __init__(self):
        self.calls = []
        self.vertexai = False
        self._api_client = SimpleNamespace(vertexai=False, _http_options=types.HttpOptions())
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._gen))

    async def _gen(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        si = str(config.system_instruction or "")
        answer = next((v for k, v in CANNED.items() if k in si), "ok")
        return types.GenerateContentResponse(candidates=[types.Candidate(
            finish_reason="STOP",
            content=types.Content(role="model", parts=[
                types.Part(text="(private reasoning that must not be shown)", thought=True),
                types.Part(text=answer),
            ]))])


def test_full_pipeline_via_gemini_api(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    import server

    fake = FakeGenAI()

    def patch(agent):
        if isinstance(agent, LlmAgent):
            m = models.build_model("gemma-4-26b-a4b-it")
            m.client = fake
            agent.model = m
        for sub in getattr(agent, "sub_agents", []) or []:
            patch(sub)

    patch(server.root_agent)
    from fastapi.testclient import TestClient

    outfit = _img_data_url(lambda x, y: (40, 50, 90) if y > 100 else (235, 230, 220))
    resp = TestClient(server.app).post("/api/fitcheck", json={
        "outfit_photo": outfit, "liked_colors": ["#1f2a44"], "occasion": "job interview"})
    lines = [json.loads(l) for l in resp.text.strip().splitlines()]
    assert not [l for l in lines if l["type"] == "error"], lines

    # 7 model calls: reader + 4 council + skeptic + head
    assert len(fake.calls) == 7
    assert {c["model"] for c in fake.calls} == {"gemma-4-26b-a4b-it"}
    # Gemma 4 → native system instructions are sent
    assert all(c["config"].system_instruction for c in fake.calls)
    # the outfit photo reaches the vision step as inline image bytes
    reader = next(c for c in fake.calls if "eyes of a fashion" in str(c["config"].system_instruction))
    mimes = [p.inline_data.mime_type for c in reader["contents"] for p in c.parts if p.inline_data]
    assert mimes == ["image/png"]
    # thinking text never leaks into the debate feed or the scorecard
    assert "private reasoning" not in resp.text
    result = lines[-1]["result"]
    assert result["parsed_ok"] and result["overall_score"] == 7.1


def test_health_never_exposes_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "super-secret-123")
    import server
    from fastapi.testclient import TestClient

    body = TestClient(server.app).get("/api/health").text
    assert "super-secret" not in body


def test_expert_with_empty_answer_does_not_crash(monkeypatch):
    """Reproduces the live bug: Gemma 4 spends its whole budget thinking and
    returns no visible text for one expert (finish_reason MAX_TOKENS)."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    import server

    fake = FakeGenAI()
    original = fake._gen

    async def gen(model, contents, config):
        if "COLOR ANALYST" in str(config.system_instruction):
            fake.calls.append({"model": model, "contents": contents, "config": config})
            return types.GenerateContentResponse(candidates=[types.Candidate(
                finish_reason="MAX_TOKENS",
                content=types.Content(role="model", parts=[
                    types.Part(text="thinking thinking thinking…", thought=True)]))])
        return await original(model, contents, config)

    fake.aio.models.generate_content = gen

    def patch(agent):
        if isinstance(agent, LlmAgent):
            m = models.build_model("gemma-4-26b-a4b-it")
            m.client = fake
            agent.model = m
        for sub in getattr(agent, "sub_agents", []) or []:
            patch(sub)

    patch(server.root_agent)
    from fastapi.testclient import TestClient

    resp = TestClient(server.app).post("/api/fitcheck", json={
        "selected_item_ids": ["t1", "b3", "s2"], "occasion": "office"})
    lines = [json.loads(l) for l in resp.text.strip().splitlines()]
    assert not [l for l in lines if l["type"] == "error"], lines
    analyst = [l for l in lines if l.get("agent") == "ColorAnalyst"]
    assert analyst and "token limit" in analyst[0]["text"]
    assert lines[-1]["type"] == "result"
    head = next(c for c in fake.calls if "HEAD STYLIST" in str(c["config"].system_instruction))
    assert "COLOR ANALYST:" in str(head["config"].system_instruction)


def test_error_messages_are_classified_correctly(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    import server
    from google.genai import errors

    # A plain KeyError containing "not found" must NOT be blamed on the model
    msg = server.explain_error(KeyError("Context variable not found: `x`"))
    assert "isn't available" not in msg and "KeyError" in msg
    assert "quota" in server.explain_error(errors.ClientError(429, {"error": {"message": "Resource exhausted"}}))
    assert "isn't available" in server.explain_error(errors.ClientError(404, {"error": {"message": "models/x not found"}}))
    assert "API key" in server.explain_error(errors.ClientError(400, {"error": {"message": "API key not valid", "status": "INVALID_ARGUMENT"}}))


def test_thinking_rejected_falls_back(monkeypatch):
    import asyncio
    from google.genai import errors
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    fake = FakeGenAI()
    seen = []

    async def gen(model, contents, config):
        seen.append(config.thinking_config)
        if config.thinking_config is not None:
            raise errors.ClientError(400, {"error": {"message": "thinking_level is not supported", "status": "INVALID_ARGUMENT"}})
        return await FakeGenAI._gen(fake, model, contents, config)

    fake.aio.models.generate_content = gen
    m = models.build_model("gemma-4-26b-a4b-it")
    m.client = fake
    req = LlmRequest(model="gemma-4-26b-a4b-it",
                     contents=[types.Content(role="user", parts=[types.Part(text="hi")])],
                     config=models.generation_config("gemma-4-26b-a4b-it", 0.5))
    req.config.system_instruction = "You are the PERSONAL STYLIST"

    async def run():
        return [r async for r in m.generate_content_async(req)]

    out = asyncio.run(run())
    assert seen[0] is not None and seen[-1] is None
    assert any(p.text and "SCORE" in p.text for r in out for p in r.content.parts)
