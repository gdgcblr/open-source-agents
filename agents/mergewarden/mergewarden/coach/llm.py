"""Gemini with an automatic fallback model on quota/overload/timeout errors."""

from __future__ import annotations

import asyncio
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
RETRY_PAUSE_S = 2.0  # before the last try, when every model was busy
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
        # Busy primary (recent failure) -> start with the fallback. Either way, if one model is busy, try the
        # other, then give the fast model one more go after a short pause before giving up.
        primary_up = time.monotonic() >= _STATE["primary_down_until"] or not self.fallback
        plan = [m for m in ([self.model, self.fallback] if primary_up else [self.fallback, self.model]) if m]
        plan.append(self.fallback or self.model)
        thinking = llm_request.config.thinking_config if llm_request.config else None
        last: Exception | None = None
        for attempt, model in enumerate(plan):
            if attempt == len(plan) - 1:
                await asyncio.sleep(RETRY_PAUSE_S)
            cfg = llm_request.config or types.GenerateContentConfig()
            llm_request.config, llm_request.model = cfg, model
            cfg.thinking_config = thinking if model == self.model else None  # lite model: its default
            original_http = cfg.http_options
            if model == self.model and self.fallback:
                cfg.http_options = types.HttpOptions(timeout=PRIMARY_TIMEOUT_MS)
            started = False
            try:
                async for r in self._gemini.generate_content_async(llm_request, stream=stream):
                    started = True
                    yield r
                return
            except (errors.APIError, httpx.TimeoutException) as e:
                if started or (isinstance(e, errors.APIError) and e.code not in RETRYABLE):
                    raise
                last = e
                if model == self.model and self.fallback:
                    _STATE["primary_down_until"] = time.monotonic() + COOLDOWN_S
                log.warning("coach model %s busy (%s); trying the next option", model, getattr(e, "code", "timeout"))
            finally:
                cfg.http_options = original_http
        raise last  # every option was busy: the service answers the student kindly
