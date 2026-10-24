"""GeminiProvider error handling, with the network call replaced by a fake."""

from types import SimpleNamespace

import pytest
from google.genai import errors

from evals import run_ai_eval
from prcheck.ai import providers
from prcheck.ai.providers import GeminiProvider, ProviderError, ProviderUnavailable, StaticProvider


def _server_error():
    return errors.ServerError(503, {"error": {"code": 503, "message": "busy", "status": "UNAVAILABLE"}})


def _client_error(code):
    return errors.ClientError(code, {"error": {"code": code, "message": "no", "status": "X"}})


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def generate_content(self, **_):
        self.calls += 1
        item = self.outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(text=item, usage_metadata=SimpleNamespace(prompt_token_count=10,
                                                                         candidates_token_count=5))


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(providers, "SERVER_RETRY_DELAYS", (0, 0))
    return GeminiProvider(model="test-model")


def use(provider, outcomes):
    fake = FakeModels(outcomes)
    provider._client = SimpleNamespace(models=fake)
    return fake


def test_missing_key_is_unavailable(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ProviderUnavailable):
        GeminiProvider()


def test_temporary_server_errors_are_retried(provider):
    fake = use(provider, [_server_error(), _server_error(), "{}"])
    response = provider.generate(system="s", prompt="p", schema={})
    assert response.text == "{}" and fake.calls == 3


def test_server_errors_give_up_after_two_retries(provider):
    fake = use(provider, [_server_error()] * 3)
    with pytest.raises(ProviderError, match="server error"):
        provider.generate(system="s", prompt="p", schema={})
    assert fake.calls == 3


@pytest.mark.parametrize("code, text", [(429, "rate limit"), (403, "API key")])
def test_client_errors_are_not_retried(provider, code, text):
    fake = use(provider, [_client_error(code)])
    with pytest.raises(ProviderError, match=text):
        provider.generate(system="s", prompt="p", schema={})
    assert fake.calls == 1


def test_injection_case_with_no_valid_runs_fails_the_eval():
    _, cases = run_ai_eval.load_golden()
    adversarial = {k: v for k, v in cases.items() if v["adversarial"]}
    result = run_ai_eval.evaluate(StaticProvider([ProviderError("quota")] * 3), adversarial, runs=3)
    assert result["injection_resisted"] is False
    assert not run_ai_eval.passes(result)
