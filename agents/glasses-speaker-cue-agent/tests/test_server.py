import pytest
from fastapi.testclient import TestClient

from glasses_speaker_cue_agent import pipeline
from glasses_speaker_cue_agent.deck import Draft
from server import MAX_BODY_BYTES, create_app

TOKEN = "t" * 32
DRAFT = {
    "title": "Why agents fail",
    "sections": [
        {"heading": "Hook", "spokenText": "Most agents fail. Here's why.", "cueKeywords": []}
    ],
    "qa": [{"question": "Q?", "answer": "A.", "fromNotes": True}],
}


@pytest.fixture
def client(monkeypatch):
    # Only the model call is replaced; guardrails and deck building run for real.
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-used")
    monkeypatch.setenv("MODEL_NAME", "model-from-env")
    sent = {}

    async def fake_run_agent(request, image, model, progress):
        sent["request"] = request
        sent["model"] = model
        return Draft.model_validate(DRAFT)

    monkeypatch.setattr(pipeline, "run_agent", fake_run_agent)
    test_client = TestClient(create_app(TOKEN))
    test_client.sent = sent
    return test_client


def _post(client, body, token=TOKEN):
    return client.post("/v1/script", json=body, headers={"X-Agent-Token": token})


def test_returns_neurallens_compatible_deck(client):
    response = _post(client, {"notes": "Why agents fail", "durationSeconds": 60})
    assert response.status_code == 200
    deck = response.json()
    assert deck["title"] == "Why agents fail"
    assert deck["sections"][0] == {
        "heading": "Hook",
        "spokenText": "Most agents fail. Here's why.",
        "cueKeywords": [],
    }
    assert deck["estimatedDurationSeconds"] > 0
    assert deck["cues"]


@pytest.mark.parametrize("token", ["", "wrong-token"])
def test_rejects_missing_or_wrong_token(client, token):
    response = _post(client, {"notes": "x", "durationSeconds": 60}, token=token)
    assert response.status_code == 401
    assert "request" not in client.sent


def test_rejects_oversized_body_before_reading_it(client):
    response = client.post(
        "/v1/script",
        content=b"x" * (MAX_BODY_BYTES + 1),
        headers={"X-Agent-Token": TOKEN, "Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_secrets_are_blocked_and_never_sent(client):
    response = _post(client, {"notes": "key " + "AIza" + "C" * 35, "durationSeconds": 60})
    assert response.status_code == 422
    assert "request" not in client.sent


def test_invalid_language_is_a_client_error(client):
    response = _post(client, {"notes": "hello", "durationSeconds": 60, "language": "xx"})
    assert response.status_code == 400


def test_pii_is_redacted_before_sending(client):
    _post(client, {"notes": "Reach me at dev@example.com", "durationSeconds": 60})
    assert "dev@example.com" not in client.sent["request"]
    assert "[EMAIL]" in client.sent["request"]


def test_rate_limit_maps_to_429(client, monkeypatch):
    async def limited(request, image, model, progress):
        raise pipeline.UpstreamError("Gemini rate limit", "rate_limited")

    monkeypatch.setattr(pipeline, "run_agent", limited)
    assert _post(client, {"notes": "hi", "durationSeconds": 60}).status_code == 429


def test_model_comes_from_settings_loaded_after_env(client):
    _post(client, {"notes": "hi", "durationSeconds": 60})
    assert client.sent["model"] == "model-from-env"


def test_chunked_body_without_length_is_refused(client):
    response = client.post(
        "/v1/script",
        content=iter([b'{"notes": "hi", ', b'"durationSeconds": 60}']),
        headers={"X-Agent-Token": TOKEN, "Content-Type": "application/json"},
    )
    assert response.status_code == 411
    assert "request" not in client.sent


def test_duration_below_minimum_is_rejected_by_schema(client):
    response = _post(client, {"notes": "hi", "durationSeconds": 20})
    assert response.status_code == 422
    assert "request" not in client.sent


def test_qa_is_dropped_in_code_when_not_requested(client):
    deck = _post(client, {"notes": "hi", "durationSeconds": 60, "includeQa": False}).json()
    assert deck["qa"] == []


def test_health_needs_no_token_and_reveals_nothing(client):
    response = client.get("/healthz")
    assert response.json() == {"ok": True}


def test_api_docs_are_not_exposed(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
