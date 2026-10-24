"""Thin Gemini wrapper.

Every caller has an offline fallback, so the whole event runs without an API key and a
failed or rate-limited call degrades a single profile or icebreaker instead of the event.
"""

from __future__ import annotations

import logging
import os
from typing import TypeVar

from pydantic import BaseModel

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Cheapest text model this project could use on the Gemini API (Oct 2026). gemini-2.5-flash-lite
# is cheaper on paper but returns 404 "no longer available to new users" for new keys.
DEFAULT_MODEL = "gemini-3.1-flash-lite"

# Errors that will fail the same way on every call (bad key, unknown model, no access).
_PERMANENT_CODES = {400, 401, 403, 404}


class LLM:
    """`mode` is "auto" (Gemini when a key is set), "offline" or "gemini" (key required)."""

    def __init__(self, mode: str | None = None, model: str | None = None, api_key: str | None = None):
        self.mode = (mode or os.getenv("LLM_MODE", "auto")).lower()
        self.model = model or os.getenv("MODEL_NAME", DEFAULT_MODEL)
        self.calls = 0
        self.failures = 0
        self._client = None

        key = api_key or os.getenv("GEMINI_API_KEY")
        if self.mode == "gemini" and not key:
            raise RuntimeError("LLM_MODE=gemini but GEMINI_API_KEY is not set")
        if self.mode != "offline" and key:
            from google import genai

            self._client = genai.Client(api_key=key)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def structured(self, prompt: str, schema: type[T]) -> T | None:
        """Return a parsed `schema` instance, or None when the LLM is off or the call fails."""
        if not self.enabled:
            return None
        from google.genai import errors, types

        self.calls += 1
        try:
            resp = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0.4,
                    # Extraction and short copy need no reasoning; thinking tokens are billed as output.
                    thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
                ),
            )
            # Read the text parts ourselves: resp.text warns about the thought_signature part.
            parts = resp.candidates[0].content.parts or []
            text = "".join(p.text for p in parts if p.text and not p.thought)
            return schema.model_validate_json(text)
        except errors.ClientError as exc:
            self.failures += 1
            if exc.code in _PERMANENT_CODES:
                # Retrying every attendee against a dead model would just spam the log.
                log.error("Gemini rejected %s (%s); switching to offline mode for this run: %s", self.model, exc.code, exc)
                self._client = None
            else:
                log.warning("Gemini call failed (%s), using offline fallback", exc.code)
            return None
        except Exception as exc:  # network, 5xx, schema drift: fall back, never break the event
            self.failures += 1
            log.warning("Gemini call failed, using offline fallback: %s", exc)
            return None
