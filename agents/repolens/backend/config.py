"""
RepoLens — Application Configuration
Loads all settings from environment variables / .env file via pydantic-settings.
"""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Gemini / Google AI
    google_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"

    # PostgreSQL
    database_url: str = "postgresql://localhost:5432/repolens"

    # Server
    host: str = "localhost"
    port: int = 8000
    log_level: str = "info"

    # Scanner limits
    max_repo_size_mb: int = 100
    scan_timeout_seconds: int = 300
    max_snippet_bytes: int = 2048

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        allowed = {"debug", "info", "warning", "error", "critical"}
        if v.lower() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v.lower()

    @property
    def gemini_available(self) -> bool:
        return bool(self.google_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
