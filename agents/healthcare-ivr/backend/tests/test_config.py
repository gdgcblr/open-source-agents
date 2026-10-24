from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import EXAMPLE_DASHBOARD_PASSWORD
from tests.conftest import make_settings


def test_example_dashboard_password_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="DASHBOARD_PASSWORD"):
        make_settings(tmp_path, dashboard_password=EXAMPLE_DASHBOARD_PASSWORD)


def test_public_urls_follow_the_configured_scheme(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, public_base_url="https://abc.ngrok-free.app/")

    assert settings.public_url("/api/twilio/voice") == "https://abc.ngrok-free.app/api/twilio/voice"
    assert settings.public_ws_url("/api/twilio/media-stream") == (
        "wss://abc.ngrok-free.app/api/twilio/media-stream"
    )


def test_unknown_timezone_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="unknown timezone"):
        make_settings(tmp_path, hospital_timezone="Mars/Olympus_Mons")
