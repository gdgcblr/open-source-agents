from __future__ import annotations

import io
import json
import urllib.error

import pytest

from context_orchestration import gateway as gw
from context_orchestration.contracts import ContextPackage, WorkerConfig
from context_orchestration.worker import UniversalWorker, WorkerOutputError, parse_claims


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def reply(content: str) -> FakeResponse:
    return FakeResponse(json.dumps({"choices": [{"message": {"content": content}}]}).encode())


def test_split_model():
    assert gw.split_model("groq/openai/gpt-oss-120b") == ("groq", "openai/gpt-oss-120b")
    assert gw.split_model("my-local-model") == (None, "my-local-model")


def test_http_gateway_shapes_the_request(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout):
        sent["url"] = request.full_url
        sent["headers"] = dict(request.header_items())
        sent["body"] = json.loads(request.data)
        return reply("{}")

    monkeypatch.setattr(gw.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("TEST_KEY", "sk-third-party")
    config = WorkerConfig(id="w", model="groq/llama-3.3-70b", api_key_env="TEST_KEY", max_tokens=99)
    assert gw.HTTPGateway().complete(config, [{"role": "user", "content": "hi"}]) == "{}"
    assert sent["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer sk-third-party"
    assert sent["body"]["model"] == "llama-3.3-70b"
    assert sent["body"]["max_tokens"] == 99


def test_http_gateway_honours_api_base(monkeypatch):
    urls = []
    monkeypatch.setattr(gw.urllib.request, "urlopen", lambda r, timeout: urls.append(r.full_url) or reply("ok"))
    config = WorkerConfig(id="w", model="anything", api_base="http://localhost:9999/v1/")
    gw.HTTPGateway().complete(config, [])
    assert urls == ["http://localhost:9999/v1/chat/completions"]


def test_http_gateway_retries_a_rate_limit(monkeypatch):
    calls, sleeps = [], []

    def fake_urlopen(request, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError(request.full_url, 429, "slow down", {"retry-after": "2"}, io.BytesIO())
        return reply("done")

    monkeypatch.setattr(gw.urllib.request, "urlopen", fake_urlopen)
    result = gw.HTTPGateway(sleep=sleeps.append).complete(WorkerConfig(id="w", model="openai/x"), [])
    assert result == "done" and sleeps == [2.0]


def test_http_errors_never_echo_the_key(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, io.BytesIO(b"invalid key"))

    monkeypatch.setattr(gw.urllib.request, "urlopen", fake_urlopen)
    config = WorkerConfig(id="w", model="openai/x", api_key="sk-secret-value")
    with pytest.raises(gw.GatewayError) as exc:
        gw.HTTPGateway().complete(config, [])
    assert "401" in str(exc.value) and "sk-secret-value" not in str(exc.value)


def test_unknown_provider_without_api_base_is_an_error():
    with pytest.raises(gw.GatewayError):
        gw.HTTPGateway().complete(WorkerConfig(id="w", model="mystery/model"), [])


def test_build_gateway(monkeypatch):
    assert isinstance(gw.build_gateway(True), gw.MockGateway)
    monkeypatch.delenv("COE_GATEWAY", raising=False)
    assert isinstance(gw.build_gateway(False), gw.HTTPGateway)
    monkeypatch.setenv("COE_GATEWAY", "litellm")
    assert isinstance(gw.build_gateway(False), gw.LiteLLMGateway)


def test_parse_claims_tolerates_prose_and_fences():
    claims = parse_claims('Sure!\n```json\n{"summary": "ok", "made_by": "me"}\n```')
    assert claims.summary == "ok"
    with pytest.raises(WorkerOutputError):
        parse_claims("no json here")


def test_a_malformed_reply_is_retried_then_reported():
    class Flaky:
        def __init__(self, replies):
            self.replies = list(replies)

        def complete(self, config, messages):
            return self.replies.pop(0)

    package = ContextPackage(task_id="t", turn=1, target_worker_id="w", assigned_task="a",
                             rendered_text="YOUR ASSIGNED TASK\n- a", estimated_tokens=5, budget=10)
    config = WorkerConfig(id="w", model="m")
    claims, _ = UniversalWorker(config, Flaky(["garbage", '{"summary": "ok"}'])).run(package)
    assert claims.summary == "ok"
    with pytest.raises(WorkerOutputError):
        UniversalWorker(config, Flaky(["bad", "worse"])).run(package)
