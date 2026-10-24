"""Limits and settings shared by the agent, the guardrails and the CLI."""

from __future__ import annotations

import os
from dataclasses import dataclass

# Display: ~3 lines of ~30 characters is comfortable on Meta Ray-Ban Display.
MAX_CUE_CHARS = 90

# Speaking rate used for every duration estimate.
DEFAULT_WPM = 150

# Agent loop limits. MAX_LLM_CALLS is the total per request, including the
# RETRY_LLM_CALLS reserved for re-asking when a reply is not valid JSON.
MAX_REVISIONS = 3
MAX_LLM_CALLS = 10
RETRY_LLM_CALLS = 2
DURATION_TOLERANCE = 0.15

# Q&A cards shown after the last cue.
QA_COUNT = 3

# Input limits.
MAX_NOTES_CHARS = 8000
MIN_MINUTES = 0.5
MAX_MINUTES = 30.0
MAX_IMAGE_BYTES = 5 * 1024 * 1024

# Languages that are written with spaces between words, so word-based timing
# works. Code -> name used in the prompt.
LANGUAGES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "kn": "Kannada",
    "ta": "Tamil",
    "te": "Telugu",
    "ml": "Malayalam",
    "mr": "Marathi",
    "bn": "Bengali",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
}

DEFAULT_MODEL = "gemini-3.5-flash"


class ConfigError(RuntimeError):
    """Required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    model: str


def load_settings() -> Settings:
    """Reads settings from the environment and fails fast if the API key is missing.

    The key itself is left in the environment for the Google GenAI client and
    is never returned, logged or printed.
    """
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        raise ConfigError(
            "GOOGLE_API_KEY is missing. Copy .env.example to .env and add your "
            "Gemini API key from https://aistudio.google.com/apikey"
        )
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")
    return Settings(model=os.environ.get("MODEL_NAME", "").strip() or DEFAULT_MODEL)
