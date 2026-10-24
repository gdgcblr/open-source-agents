import json
import pytest
from google.genai import errors

from firstrun import llm as llm_mod
from firstrun.llm import FakeLLM, GeminiLLM, LLMError, get_llm, parse_json


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate_content(self, *, model, contents, config=None):
        self.calls.append({"model": model, "contents": contents, "config": config})
        item = self.outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)


class FakeClient:
    def __init__(self, outcomes):
        self.models = FakeModels(outcomes)


def api_error(code, status="ERROR"):
    return errors.APIError(code, {"error": {"code": code, "message": "boom", "status": status}})


def test_parse_json_plain_fenced_and_wrapped():
    assert parse_json('{"a": 1}') == {"a": 1}
    assert parse_json('```json\n{"a": 2}\n```') == {"a": 2}
    assert parse_json('Here you go: {"a": 3} hope that helps') == {"a": 3}


def test_parse_json_rejects_non_objects():
    with pytest.raises(LLMError):
        parse_json("definitely not json")
    with pytest.raises(LLMError):
        parse_json("[1, 2, 3]")
    with pytest.raises(LLMError):
        parse_json(None)


def test_gemini_builds_multi_turn_request():
    client = FakeClient(['{"ok": true}'])
    g = GeminiLLM(model="gemini-test", client=client)
    out = g.complete_json("be terse", [
        {"role": "user", "text": "hello"},
        {"role": "model", "text": "{}"},
        {"role": "user", "text": "again"},
    ])
    assert out == {"ok": True}
    call = client.models.calls[0]
    assert call["model"] == "gemini-test"
    assert [c.role for c in call["contents"]] == ["user", "model", "user"]
    assert call["contents"][2].parts[0].text == "again"
    cfg = call["config"]
    assert cfg.system_instruction == "be terse"
    assert cfg.response_mime_type == "application/json"
    assert cfg.temperature == 0.2
    assert g.name == "gemini:gemini-test"


def test_gemini_retries_rate_limits_then_succeeds():
    client = FakeClient([api_error(429, "RESOURCE_EXHAUSTED"), api_error(503), '{"done": 1}'])
    g = GeminiLLM(model="m", client=client, retries=2, backoff=0)
    assert g.complete_json("s", [{"role": "user", "text": "x"}]) == {"done": 1}
    assert len(client.models.calls) == 3


def test_gemini_gives_up_after_retries():
    client = FakeClient([api_error(429)] * 3)
    g = GeminiLLM(model="m", client=client, retries=2, backoff=0)
    with pytest.raises(LLMError, match="429"):
        g.complete_json("s", [{"role": "user", "text": "x"}])


def test_gemini_does_not_retry_client_errors():
    client = FakeClient([api_error(400, "INVALID_ARGUMENT"), '{"never": 1}'])
    g = GeminiLLM(model="m", client=client, backoff=0)
    with pytest.raises(LLMError, match="400"):
        g.complete_json("s", [{"role": "user", "text": "x"}])
    assert len(client.models.calls) == 1


def test_gemini_non_json_reply_is_a_clear_error():
    g = GeminiLLM(model="m", client=FakeClient(["I think the answer is yes"]))
    with pytest.raises(LLMError, match="not JSON"):
        g.complete_json("s", [{"role": "user", "text": "x"}])


def test_gemini_model_from_env(monkeypatch):
    monkeypatch.setenv("FIRSTRUN_MODEL", "gemini-from-env")
    assert GeminiLLM(client=FakeClient([])).model == "gemini-from-env"
    monkeypatch.delenv("FIRSTRUN_MODEL")
    assert GeminiLLM(client=FakeClient([])).model == llm_mod.DEFAULT_MODEL == "gemini-flash-latest"


def test_gemini_without_key_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(LLMError, match="API key"):
        GeminiLLM()


def test_get_llm(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert get_llm() is None
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    assert get_llm(offline=True) is None
    made = get_llm()
    assert isinstance(made, GeminiLLM)


def test_fake_llm_replays_and_records():
    boom = LLMError("nope")
    fake = FakeLLM([{"a": 1}, '{"b": 2}', boom])
    assert fake.complete_json("sys", [{"role": "user", "text": "1"}]) == {"a": 1}
    assert fake.complete_json("sys", [{"role": "user", "text": "2"}]) == {"b": 2}
    with pytest.raises(LLMError):
        fake.complete_json("sys", [])
    with pytest.raises(LLMError, match="ran out"):
        fake.complete_json("sys", [])
    assert len(fake.calls) == 4
    assert fake.calls[1]["messages"][0]["text"] == "2"


class _Resp:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self.body).encode()


def test_groq_sends_chat_json_and_parses_reply(monkeypatch):
    from firstrun.llm import GroqLLM

    seen = {}

    def opener(req, timeout=0):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())
        seen["payload"] = json.loads(req.data)
        return _Resp({"choices": [{"message": {"content": '{"tool": "read_file", "args": {"path": "main.py"}}'}}]})

    monkeypatch.delenv("FIRSTRUN_MODEL", raising=False)
    llm = GroqLLM(api_key="gsk_test", opener=opener)
    out = llm.complete_json("Reply in JSON.", [{"role": "user", "text": "hi"}, {"role": "model", "text": "{}"}])
    assert out == {"tool": "read_file", "args": {"path": "main.py"}}
    assert seen["url"].endswith("/openai/v1/chat/completions")
    assert seen["headers"]["Authorization"] == "Bearer gsk_test"
    assert seen["payload"]["model"] == "openai/gpt-oss-120b"
    assert [m["role"] for m in seen["payload"]["messages"]] == ["system", "user", "assistant"]
    assert seen["payload"]["response_format"] == {"type": "json_object"}
    assert llm.name == "groq:openai/gpt-oss-120b"


def test_groq_retries_without_json_mode_when_validation_fails():
    import io
    import urllib.error

    from firstrun.llm import GroqLLM

    calls = []

    def opener(req, timeout=0):
        payload = json.loads(req.data)
        calls.append("response_format" in payload)
        if "response_format" in payload:
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b'{"error":{"code":"json_validate_failed"}}'))
        return _Resp({"choices": [{"message": {"content": 'Sure: {"final": {"category": "unknown"}}'}}]})

    out = GroqLLM(api_key="k", opener=opener).complete_json("JSON please", [{"role": "user", "text": "x"}])
    assert out == {"final": {"category": "unknown"}}
    assert calls == [True, False]


def test_get_llm_provider_choice(monkeypatch):
    from firstrun import llm as mod

    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "FIRSTRUN_PROVIDER", "FIRSTRUN_MODEL"):
        monkeypatch.delenv(k, raising=False)
    assert mod.get_llm() is None
    monkeypatch.setenv("GROQ_API_KEY", "gsk_x")
    assert mod.get_llm().name.startswith("groq:")
    assert mod.get_llm(offline=True) is None
    monkeypatch.setenv("FIRSTRUN_PROVIDER", "gemini")
    assert mod.get_llm() is None  # asked for gemini, no gemini key
