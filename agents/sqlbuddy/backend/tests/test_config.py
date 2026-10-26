"""Configuration tests use a temporary fake .env file, never the real key."""

import os

from backend.app import config


def test_backend_environment_loader_reads_configured_file(tmp_path, monkeypatch):
    fake_env = tmp_path / ".env"
    fake_env.write_text("GEMINI_API_KEY=sqlbuddy-test-value\n", encoding="utf-8")
    monkeypatch.setattr(config, "BACKEND_ENV_FILE", fake_env)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    config.load_backend_environment()

    assert os.environ.get("GEMINI_API_KEY") == "sqlbuddy-test-value"
