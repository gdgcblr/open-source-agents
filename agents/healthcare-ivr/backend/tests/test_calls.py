from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.deepgram import DeepgramDiarizer, DeepgramError, DiarizationResult
from tests.conftest import DASHBOARD_AUTH, make_settings

AUDIO = b"RIFF-fake-wav-bytes"


def _upload(client: TestClient, name: str = "support-call.wav", data: bytes = AUDIO) -> dict:
    response = client.post("/api/calls/upload", files={"file": (name, data, "audio/wav")})
    assert response.status_code == 201, response.text
    return response.json()


def test_health_does_not_require_auth(client: TestClient) -> None:
    response = client.get("/api/health", auth=None)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_calls_require_basic_auth(client: TestClient) -> None:
    response = client.get("/api/calls", auth=None)

    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")


def test_calls_reject_wrong_password(client: TestClient) -> None:
    response = client.get("/api/calls", auth=(DASHBOARD_AUTH[0], "wrong"))

    assert response.status_code == 401


def test_uploaded_recording_is_diarized(
    client: TestClient, fake_deepgram: list[tuple[bytes, str]]
) -> None:
    created = _upload(client)

    assert created["source"] == "upload"
    assert created["title"] == "support-call.wav"
    assert created["has_audio"] is True
    assert fake_deepgram == [(AUDIO, "audio/wav")]

    detail = client.get(f"/api/calls/{created['id']}").json()
    assert detail["diarization_status"] == "completed"
    assert detail["speaker_count"] == 2
    assert detail["duration_seconds"] == pytest.approx(18.4)
    assert [u["speaker"] for u in detail["utterances"]] == [0, 1, 0, 1]
    assert detail["utterances"][1] == {
        "speaker": 1,
        "start": 4.8,
        "end": 8.9,
        "text": "Hi, when is the cardiology OPD open this week?",
        "confidence": 0.94,
    }
    assert detail["turns"] == []
    # 18.4 seconds of audio at $0.0052 per minute (multilingual); uploads have no agent cost.
    assert detail["transcription_cost_usd"] == 0.0016
    assert detail["agent_cost_usd"] is None
    assert detail["total_cost_usd"] == 0.0016


def test_upload_rejects_non_audio_files(client: TestClient) -> None:
    response = client.post(
        "/api/calls/upload", files={"file": ("notes.txt", b"hello", "text/plain")}
    )

    assert response.status_code == 415


def test_upload_rejects_files_over_the_size_limit(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, max_upload_mb=0)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/calls/upload",
            files={"file": ("call.wav", AUDIO, "audio/wav")},
            auth=DASHBOARD_AUTH,
        )

    assert response.status_code == 413
    assert list(settings.recordings_dir.iterdir()) == []


def test_failed_diarization_is_recorded(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_diarize(self: DeepgramDiarizer, audio: bytes, ct: str) -> DiarizationResult:
        raise DeepgramError("Deepgram returned HTTP 401: invalid credentials")

    monkeypatch.setattr(DeepgramDiarizer, "diarize", failing_diarize)

    created = _upload(client)
    detail = client.get(f"/api/calls/{created['id']}").json()

    assert detail["diarization_status"] == "failed"
    assert "HTTP 401" in detail["diarization_error"]


def test_audio_can_be_played_then_deleted(
    client: TestClient, settings: Settings, fake_deepgram: list[tuple[bytes, str]]
) -> None:
    created = _upload(client)

    audio = client.get(f"/api/calls/{created['id']}/audio")
    assert audio.status_code == 200
    assert audio.content == AUDIO
    assert audio.headers["content-type"] == "audio/wav"

    assert client.delete(f"/api/calls/{created['id']}").status_code == 204
    assert client.get(f"/api/calls/{created['id']}").status_code == 404
    assert list(settings.recordings_dir.iterdir()) == []


def test_calls_are_listed_newest_first_with_pagination(
    client: TestClient, fake_deepgram: list[tuple[bytes, str]]
) -> None:
    for name in ("first.wav", "second.wav", "third.wav"):
        _upload(client, name=name)

    first_page = client.get("/api/calls", params={"page": 1, "page_size": 2}).json()
    second_page = client.get("/api/calls", params={"page": 2, "page_size": 2}).json()

    assert first_page["total"] == 3
    assert first_page["total_cost_usd"] == 0.0048  # three uploads at 0.0016 each
    assert [c["title"] for c in first_page["items"]] == ["third.wav", "second.wav"]
    assert [c["title"] for c in second_page["items"]] == ["first.wav"]
