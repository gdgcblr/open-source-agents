from pathlib import Path
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security import create_stream_token
from tests.conftest import TWILIO_AUTH_TOKEN, make_settings, signed_twilio_post

CALL_SID = "CA00000000000000000000000000000001"
RECORDING_URL = "https://api.twilio.com/2010-04-01/Accounts/ACtest/Recordings/RE0001"


def _answer(client: TestClient) -> None:
    response = signed_twilio_post(
        client, "/api/twilio/voice", {"CallSid": CALL_SID, "From": "+15550100"}
    )
    assert response.status_code == 200, response.text


def test_voice_webhook_rejects_unsigned_requests(client: TestClient) -> None:
    response = client.post("/api/twilio/voice", data={"CallSid": CALL_SID}, auth=None)

    assert response.status_code == 403


def test_voice_webhook_requires_twilio_configuration(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, twilio_account_sid="", twilio_auth_token="")
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/twilio/voice", data={"CallSid": CALL_SID})

    assert response.status_code == 503


def test_voice_webhook_connects_caller_to_media_stream(client: TestClient) -> None:
    response = signed_twilio_post(
        client, "/api/twilio/voice", {"CallSid": CALL_SID, "From": "+15550100"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    twiml = ElementTree.fromstring(response.text)
    stream = twiml.find("./Connect/Stream")
    assert stream is not None
    assert stream.get("url") == "wss://reception.example.com/api/twilio/media-stream"
    parameter = stream.find("Parameter")
    assert parameter is not None
    assert parameter.get("name") == "token"
    assert parameter.get("value") == create_stream_token(CALL_SID, TWILIO_AUTH_TOKEN)
    assert twiml.find("Say") is not None  # fallback if the agent is unreachable

    [call] = client.get("/api/calls").json()["items"]
    assert call["source"] == "phone"
    assert call["status"] == "in_progress"
    assert call["caller_number"] == "+15550100"
    assert call["diarization_status"] == "pending"


def test_voice_webhook_retries_do_not_duplicate_calls(client: TestClient) -> None:
    _answer(client)
    _answer(client)

    assert client.get("/api/calls").json()["total"] == 1


def test_completed_recording_is_downloaded_and_diarized(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_deepgram: list[tuple[bytes, str]],
) -> None:
    downloaded: list[str] = []

    async def fake_download(settings: Settings, recording_url: str) -> bytes:
        downloaded.append(recording_url)
        return b"mp3-bytes"

    monkeypatch.setattr("app.services.diarization.download_recording", fake_download)
    _answer(client)

    response = signed_twilio_post(
        client,
        "/api/twilio/recording-status",
        {
            "CallSid": CALL_SID,
            "RecordingSid": "RE0001",
            "RecordingUrl": RECORDING_URL,
            "RecordingStatus": "completed",
        },
    )

    assert response.status_code == 204
    assert downloaded == [RECORDING_URL]
    assert fake_deepgram == [(b"mp3-bytes", "audio/mpeg")]
    [call] = client.get("/api/calls").json()["items"]
    detail = client.get(f"/api/calls/{call['id']}").json()
    assert detail["has_audio"] is True
    assert detail["diarization_status"] == "completed"
    assert len(detail["utterances"]) == 4


@pytest.mark.parametrize("withheld", ["+266696687", "+7378742833", "anonymous", ""])
def test_withheld_caller_ids_are_stored_as_unknown(client: TestClient, withheld: str) -> None:
    # Every caller who hides their number shares these values, so they can't identify a patient.
    signed_twilio_post(client, "/api/twilio/voice", {"CallSid": CALL_SID, "From": withheld})

    [call] = client.get("/api/calls").json()["items"]
    assert call["caller_number"] is None


def test_recordings_outside_twilio_are_not_fetched(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail_download(settings: Settings, recording_url: str) -> bytes:
        raise AssertionError("must not send Twilio credentials to another host")

    monkeypatch.setattr("app.services.diarization.download_recording", fail_download)
    _answer(client)

    response = signed_twilio_post(
        client,
        "/api/twilio/recording-status",
        {
            "CallSid": CALL_SID,
            "RecordingSid": "RE0001",
            "RecordingUrl": "https://api.twilio.com.attacker.example/Recordings/RE0001",
            "RecordingStatus": "completed",
        },
    )

    assert response.status_code == 204
    [call] = client.get("/api/calls").json()["items"]
    assert call["diarization_status"] == "failed"


def test_absent_recording_marks_diarization_failed(client: TestClient) -> None:
    _answer(client)

    response = signed_twilio_post(
        client,
        "/api/twilio/recording-status",
        {"CallSid": CALL_SID, "RecordingSid": "RE0001", "RecordingStatus": "absent"},
    )

    assert response.status_code == 204
    [call] = client.get("/api/calls").json()["items"]
    assert call["diarization_status"] == "failed"
