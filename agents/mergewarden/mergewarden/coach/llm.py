"""Gemini with an automatic fallback model on quota/overload/timeout errors."""

from __future__ import annotations

import logging
import time
from typing import AsyncGenerator

import httpx
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.models._capabilities import LlmCapabilities
from google.adk.models.google_llm import Gemini
from google.genai import errors, types

from . import config

log = logging.getLogger(__name__)
RETRYABLE = {429, 500, 503, 504}
PRIMARY_TIMEOUT_MS = 15_000  # a chat reply that takes longer is better served by the fallback
COOLDOWN_S = 300  # after a failure, skip the primary for a while instead of waiting on it every turn
_STATE = {"primary_down_until": 0.0}


class FallbackGemini(BaseLlm):
    """Calls `model`; on 429/5xx/timeout before any output, retries on `fallback`."""

    fallback: str = config.FALLBACK_MODEL

    @property
    def capabilities(self) -> LlmCapabilities:
        return Gemini(model=self.model).capabilities

    @property
    def _gemini(self) -> Gemini:
        if not hasattr(self, "_g"):
            object.__setattr__(self, "_g", Gemini(model=self.model))
        return self._g  # type: ignore[attr-defined]

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        if time.monotonic() >= _STATE["primary_down_until"] or not self.fallback:
            llm_request.model = self.model
            cfg = llm_request.config or types.GenerateContentConfig()
            original_http = cfg.http_options
            cfg.http_options = types.HttpOptions(timeout=PRIMARY_TIMEOUT_MS)
            llm_request.config = cfg
            try:
                async for r in self._gemini.generate_content_async(llm_request, stream=stream):
                    yield r
                return
            except (errors.APIError, httpx.TimeoutException) as e:
                code = getattr(e, "code", "timeout")
                if (isinstance(e, errors.APIError) and e.code not in RETRYABLE) or not self.fallback:
                    raise
                _STATE["primary_down_until"] = time.monotonic() + COOLDOWN_S
                log.warning("coach model %s failed (%s); using %s for %ss", self.model, code, self.fallback, COOLDOWN_S)
            finally:
                cfg.http_options = original_http
        llm_request.model = self.fallback
        if llm_request.config and llm_request.config.thinking_config:
            llm_request.config.thinking_config = None  # let the lite model use its default
        async for r in self._gemini.generate_content_async(llm_request, stream=stream):
            yield r
