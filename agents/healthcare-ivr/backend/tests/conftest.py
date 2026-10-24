"""Shared fixtures: every test gets an isolated app with its own SQLite database and storage."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from twilio.request_validator import RequestValidator

from app.config import Settings
from app.main import create_app
from app.services.deepgram import DeepgramDiarizer, DiarizationResult, parse_diarized_response

FIXTURES = Path(__file__).parent / "fixtures"
KNOWLEDGE_DIR = Path(__file__).parents[1] / "knowledge"
# A small, stable hospital so tests don't change when the shipped hospital data is edited.
TEST_HOSPITAL_DIR = FIXTURES / "hospital"
DASHBOARD_AUTH = ("admin", "test-password")
TWILIO_AUTH_TOKEN = "twilio-test-token"
PUBLIC_BASE_URL = "https://reception.example.com"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        "recordings_dir": tmp_path / "recordings",
        "public_base_url": PUBLIC_BASE_URL,
        "dashboard_username": DASHBOARD_AUTH[0],
        "dashboard_password": DASHBOARD_AUTH[1],
        "deepgram_api_key": "deepgram-test-key",
        "twilio_account_sid": "ACtest",
        "twilio_auth_token": TWILIO_AUTH_TOKEN,
        "hospital_dir": TEST_HOSPITAL_DIR,
        **overrides,
    }
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def signed_twilio_post(client: TestClient, path: str, params: dict[str, str]) -> Response:
    """POST form data signed exactly as Twilio would sign it for our public URL."""
    signature = RequestValidator(TWILIO_AUTH_TOKEN).compute_signature(
        PUBLIC_BASE_URL + path, params
    )
    return client.post(path, data=params, headers={"X-Twilio-Signature": signature}, auth=None)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        test_client.auth = DASHBOARD_AUTH
        yield test_client


@pytest.fixture
def fake_deepgram(monkeypatch: pytest.MonkeyPatch) -> list[tuple[bytes, str]]:
    """Replace Deepgram with a canned diarization; returns the (audio, content_type) it received."""
    received: list[tuple[bytes, str]] = []

    async def fake_diarize(
        self: DeepgramDiarizer, audio: bytes, content_type: str
    ) -> DiarizationResult:
        received.append((audio, content_type))
        return parse_diarized_response(load_fixture("deepgram_diarized_call.json"))

    monkeypatch.setattr(DeepgramDiarizer, "diarize", fake_diarize)
    return received
