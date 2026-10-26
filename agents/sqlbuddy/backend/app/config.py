"""Environment based settings for the SQLBuddy API."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ENV_FILE = PROJECT_ROOT / "backend" / ".env"


def load_backend_environment() -> None:
    """Load backend-only secrets from the project's backend/.env file."""
    load_dotenv(BACKEND_ENV_FILE)


load_backend_environment()


def _positive_int(name: str, default: int, *, maximum: int) -> int:
    """Read a bounded positive integer setting, falling back safely."""
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if 1 <= value <= maximum else default


@dataclass(frozen=True)
class Settings:
    """Application configuration; secrets are never returned by API routes."""

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    database_path: str = os.getenv(
        "SQLBUDDY_DATABASE_PATH", str(PROJECT_ROOT / "data" / "sqlbuddy.db")
    )
    frontend_origin: str = os.getenv("SQLBUDDY_FRONTEND_ORIGIN", "http://localhost:5173")
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    rate_limit_requests: int = _positive_int("SQLBUDDY_RATE_LIMIT_REQUESTS", 20, maximum=10000)
    rate_limit_window_seconds: int = _positive_int(
        "SQLBUDDY_RATE_LIMIT_WINDOW_SECONDS", 60, maximum=86400
    )
    request_timeout_seconds: int = _positive_int(
        "SQLBUDDY_REQUEST_TIMEOUT_SECONDS", 120, maximum=300
    )
    max_question_chars: int = _positive_int("SQLBUDDY_MAX_QUESTION_CHARS", 4000, maximum=20000)
    max_schema_chars: int = _positive_int("SQLBUDDY_MAX_SCHEMA_CHARS", 12000, maximum=50000)


settings = Settings()
