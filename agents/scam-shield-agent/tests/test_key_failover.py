"""API-key failover tests. The AI pipeline is stubbed; Gemini is never called."""

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from google.genai import errors  # noqa: E402

import server  # noqa: E402

SCAM_TEXT = "Share the OTP to stop your account being blocked"
VERDICT = {"verdict": "scam", "risk_score": 95, "scam_type": "OTP fraud", "summary": "Scam.",
           "red_flags": ["Asks for OTP"], "advice": ["Do not share the OTP"]}


def invalid_key():
    return errors.ClientError(400, {"error": {
        "code": 400, "status": "INVALID_ARGUMENT", "message": "API key not valid. Please pass a valid API key."}})


def over_quota(seconds=None):
    message = "You exceeded your current quota."
    if seconds:
        message += f" Please retry in {seconds}s."
    return errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": message}})


def server_down():
    return errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "Overloaded"}})


def bad_input():
    return errors.ClientError(400, {"error": {
        "code": 400, "status": "INVALID_ARGUMENT", "message": "Request contains an invalid argument."}})


def make_keys(n):
    return [f"test-secret-key-{i:02d}-abcdef" for i in range(1, n + 1)]


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def ai(monkeypatch):
    """Installs a key pool and a fake pipeline. Returns a helper with .calls and .fail."""

    class Fake:
        calls: list[int] = []
        fail: dict[int, object] = {}  # key index -> exception factory
        clock = Clock()

        def setup(self, keys):
            monkeypatch.setattr(server, "key_pool", server.KeyPool(keys, clock=self.clock))
            return TestClient(server.app)

    fake = Fake()
    fake.calls, fake.fail = [], {}

    async def fake_run_agent(runner, text, image, mime, language, simple):
        fake.calls.append(runner)
        if runner in fake.fail:
            raise fake.fail[runner]()
        return dict(VERDICT)

    monkeypatch.setattr(server, "_runner_for", lambda i: i)
    monkeypatch.setattr(server, "run_agent", fake_run_agent)
    monkeypatch.setattr(server, "_hits", server.defaultdict(server.deque))
    return fake


def check(client, **body):
    return client.post("/api/check", json={"text": SCAM_TEXT, **body})


@pytest.mark.parametrize("n", [1, 3, 8])
def test_works_with_any_number_of_keys(ai, n):
    client = ai.setup(make_keys(n))
    res = check(client)
    assert res.status_code == 200 and res.json()["mode"] == "ai"
    assert ai.calls == [0]
    assert client.get("/api/health").json().items() >= {"keys_total": n, "keys_available": n}.items()


@pytest.mark.parametrize("n", [3, 8])
def test_last_key_is_reached_when_all_others_are_invalid(ai, n):
    client = ai.setup(make_keys(n))
    ai.fail = {i: invalid_key for i in range(n - 1)}
    assert check(client).json()["mode"] == "ai"
    assert ai.calls == list(range(n))


def test_invalid_first_key_fails_over_and_later_requests_start_from_working_key(ai):
    client = ai.setup(make_keys(3))
    ai.fail = {0: invalid_key}
    assert check(client).json()["mode"] == "ai"
    assert ai.calls == [0, 1]
    ai.calls.clear()
    assert check(client).json()["mode"] == "ai"
    assert ai.calls == [1]
    health = client.get("/api/health").json()
    assert health["keys_total"] == 3 and health["keys_available"] == 2


def test_quota_puts_key_on_cooldown_until_it_expires(ai):
    client = ai.setup(make_keys(2))
    ai.fail = {0: lambda: over_quota(30)}
    assert check(client).json()["mode"] == "ai"
    assert ai.calls == [0, 1]
    assert server.key_pool.status(0) == "quota"

    # Key #2 now fails too: key #1 is still cooling down, so it is skipped.
    ai.fail = {0: lambda: over_quota(30), 1: server_down}
    ai.calls.clear()
    res = check(client).json()
    assert ai.calls == [1]
    assert res["mode"] == "rules" and res["ai_error"]["code"] == "all_keys_failed"

    # After the cooldown, key #1 is tried again (and now works).
    ai.clock.now += 31
    ai.fail = {1: server_down}
    ai.calls.clear()
    assert check(client).json()["mode"] == "ai"
    assert ai.calls == [1, 0]


def test_quota_without_retry_hint_uses_default_cooldown(ai):
    client = ai.setup(make_keys(2))
    ai.fail = {0: over_quota}
    check(client)
    ai.clock.now += server.QUOTA_COOLDOWN_SECONDS - 1
    assert server.key_pool.status(0) == "quota"
    ai.clock.now += 2
    assert server.key_pool.status(0) == "ok"


def test_server_errors_do_not_disable_keys(ai):
    client = ai.setup(make_keys(2))
    ai.fail = {0: server_down}
    assert check(client).json()["mode"] == "ai"
    assert ai.calls == [0, 1]
    assert server.key_pool.available() == 2


def test_other_errors_stop_without_burning_through_keys(ai):
    client = ai.setup(make_keys(3))
    ai.fail = {0: bad_input}
    res = check(client).json()
    assert ai.calls == [0]
    assert res["mode"] == "rules"
    assert server.key_pool.available() == 3


def test_all_keys_failing_returns_rules_with_counts(ai):
    client = ai.setup(make_keys(4))
    ai.fail = {0: invalid_key, 1: over_quota, 2: server_down, 3: invalid_key}
    res = check(client)
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "rules" and body["verdict"] in ("scam", "suspicious")
    err = body["ai_error"]
    assert err["code"] == "all_keys_failed"
    assert err["message"] == ("AI unavailable: all 4 API keys failed (2 invalid, 1 over quota, "
                              "1 unreachable). Update GOOGLE_API_KEYS in .env.")
    assert err["keys"] == [{"n": 1, "status": "invalid"}, {"n": 2, "status": "quota"},
                           {"n": 3, "status": "unreachable"}, {"n": 4, "status": "invalid"}]
    assert client.get("/api/health").json()["keys_available"] == 1  # only the 5xx key


def test_image_only_with_all_keys_failing_is_503(ai):
    client = ai.setup(make_keys(2))
    ai.fail = {0: invalid_key, 1: over_quota}
    res = client.post("/api/check", json={"text": "", "image_base64": "aGVsbG8=", "image_mime": "image/png"})
    assert res.status_code == 503
    assert res.json()["detail"].startswith("AI unavailable: all 2 API keys failed (1 invalid, 1 over quota")


def test_no_keys_falls_back_with_no_keys_error(ai, monkeypatch):
    client = ai.setup([])
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    body = check(client).json()
    assert body["mode"] == "rules" and body["ai_error"]["code"] == "no_keys"
    assert ai.calls == []
    assert client.get("/api/health").json().items() >= {"ai": False, "keys_total": 0, "keys_available": 0}.items()


def test_key_loading(monkeypatch):
    for var in ("GOOGLE_API_KEYS", "GOOGLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert server.load_api_keys() == []

    monkeypatch.setenv("GOOGLE_API_KEY", "single")
    assert server.load_api_keys() == ["single"]  # old single-key setup still works

    monkeypatch.setenv("GOOGLE_API_KEYS", " a, b ,, a ,single, c ")
    assert server.load_api_keys() == ["a", "b", "single", "c"]  # blanks and duplicates dropped

    monkeypatch.setenv("GOOGLE_API_KEY", "d")
    assert server.load_api_keys() == ["a", "b", "single", "c", "d"]  # single key appended last

    monkeypatch.setenv("GOOGLE_API_KEYS", ",".join(f"k{i}" for i in range(25)))
    assert len(server.load_api_keys()) == 26  # no maximum

    monkeypatch.delenv("GOOGLE_API_KEYS")
    monkeypatch.setenv("GOOGLE_API_KEY", "x, y ,z")
    assert server.load_api_keys() == ["x", "y", "z"]  # a list in the old variable also works


def test_single_google_api_key_setup_runs_ai(ai, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEYS", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-secret-key-single")
    client = ai.setup(server.load_api_keys())
    assert check(client).json()["mode"] == "ai"
    assert client.get("/api/health").json()["keys_total"] == 1


def test_each_key_gets_its_own_cached_pipeline(monkeypatch):
    keys = make_keys(2)
    monkeypatch.setattr(server, "key_pool", server.KeyPool(keys))
    monkeypatch.setattr(server, "_runners", {})
    first, second = server._runner_for(0), server._runner_for(1)
    assert first is server._runner_for(0) and first is not second
    for runner, key in ((first, keys[0]), (second, keys[1])):
        model = runner.agent.sub_agents[1].model
        assert model.client_kwargs == {"api_key": key}


def test_classify_error_unwraps_groups_and_timeouts():
    import httpx

    assert server.classify_error(ExceptionGroup("g", [invalid_key()]))[0] == "invalid"
    assert server.classify_error(errors.ClientError(403, {"error": {"message": "denied"}}))[0] == "invalid"
    assert server.classify_error(over_quota(12.5)) == ("quota", 12.5)
    assert server.classify_error(httpx.ReadTimeout("slow"))[0] == "unreachable"
    try:
        try:
            raise server_down()
        except Exception as exc:
            raise RuntimeError("wrapped") from exc
    except RuntimeError as wrapped:
        assert server.classify_error(wrapped)[0] == "unreachable"
    assert server.classify_error(ValueError("bad schema"))[0] == "other"


def test_no_key_text_in_responses_health_or_logs(ai, caplog):
    keys = make_keys(3)
    client = ai.setup(keys)
    ai.fail = {0: invalid_key, 1: lambda: over_quota(5), 2: server_down}
    with caplog.at_level(logging.DEBUG):
        outputs = [check(client).text, client.get("/api/health").text,
                   client.post("/api/check", json={"text": "", "image_base64": "aGVsbG8="}).text]
    ai.fail = {}
    ai.clock.now += 10
    outputs.append(check(client).text)
    everything = "\n".join(outputs) + caplog.text
    assert "AI key #1 failed: invalid" in caplog.text
    for key in keys:
        assert key not in everything
        assert key[-10:] not in everything
