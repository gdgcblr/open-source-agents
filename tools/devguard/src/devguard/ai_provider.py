"""Minimal AI provider adapter for DevGuard commit message generation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol


class AIProvider(Protocol):
    """Protocol for AI text generation providers."""
    def generate(self, prompt: str) -> str:
        ...


def _load_env_file() -> None:
    """Best-effort loader for .env files without requiring python-dotenv."""
    for candidate in [Path(".env"), Path("tools/devguard/.env"), Path(__file__).resolve().parents[2] / ".env"]:
        if candidate.exists() and candidate.is_file():
            try:
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
            except Exception:
                pass


class GeminiProvider:
    """Google Gemini model adapter using the official google-genai SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        load_dotenv: bool = True,
    ) -> None:
        if load_dotenv:
            _load_env_file()
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key or key == "your_gemini_api_key_here":
            raise ValueError(
                "GEMINI_API_KEY is not configured. Set GEMINI_API_KEY in your environment "
                "or .env file, or use --fallback for deterministic message generation."
            )

        self.api_key = key
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:
                raise RuntimeError(
                    "Optional dependency 'google-genai' is not installed. "
                    "Install it using: pip install 'devguard[ai]', or run with --fallback."
                ) from exc
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def generate(self, prompt: str) -> str:
        """Send prompt to Gemini model and return response text."""
        client = self._get_client()
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            return (response.text or "").strip()
        except Exception as exc:
            raise RuntimeError(f"Gemini API request failed: {exc}") from exc

