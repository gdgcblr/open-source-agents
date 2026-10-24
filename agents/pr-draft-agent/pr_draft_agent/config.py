"""Explicit project-local configuration loading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class ConfigError(Exception):
    """A local configuration failure with a stable, non-secret code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Settings:
    """Non-secret runtime settings. Credentials stay in the environment."""

    model: str | None


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def load_settings(require_model: bool) -> Settings:
    """Load this project's .env without overriding the process environment.

    When ``require_model`` is true, generation prerequisites are checked and
    failure raises ConfigError before any repository data is sent to the model.
    """
    load_dotenv(ENV_FILE, override=False)

    model = os.environ.get("PR_DRAFT_MODEL", "").strip() or None
    if not require_model:
        return Settings(model=model)

    if _truthy(os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")):
        raise ConfigError(
            "VERTEX_UNSUPPORTED",
            "Vertex AI mode is not supported. Disable GOOGLE_GENAI_USE_VERTEXAI "
            "and use GOOGLE_API_KEY.",
        )
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        raise ConfigError(
            "MISSING_CREDENTIALS",
            f"GOOGLE_API_KEY is not set. Add it to {ENV_FILE} or the process environment.",
        )
    if model is None:
        raise ConfigError(
            "MISSING_MODEL",
            "PR_DRAFT_MODEL is not set. Choose a Gemini model that supports function calling.",
        )
    return Settings(model=model)
