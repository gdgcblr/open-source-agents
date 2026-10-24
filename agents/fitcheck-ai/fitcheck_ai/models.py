"""Model selection for FitCheck AI.

Two ways to run Gemma:

  * Hosted (default when an API key is set) — Gemma via the Gemini API / Google
    AI Studio. No GPU, no downloads; just GOOGLE_API_KEY.
        gemma-4-*  → ADK `Gemini` class (native system instructions + vision)
        gemma-3-*  → ADK `Gemma` class (moves system instructions into the prompt)
  * Local — Gemma via Ollama through LiteLLM, e.g. "ollama_chat/gemma3:4b".

Everything is driven by env vars; see .env.example.
"""

from __future__ import annotations

import os

from google.adk.models.gemma_llm import Gemma
from google.adk.models.google_llm import Gemini
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.genai import types

HOSTED_DEFAULT = "gemma-4-26b-a4b-it"   # MoE: fast & cheap, strong enough for styling
LOCAL_DEFAULT = "ollama_chat/gemma3:4b"


def api_key() -> str | None:
    return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")


def default_model() -> str:
    return HOSTED_DEFAULT if api_key() else LOCAL_DEFAULT


def is_hosted(model_id: str) -> bool:
    return model_id.startswith("gemma-")


def provider_label(model_id: str) -> str:
    return "Gemini API" if is_hosted(model_id) else "Ollama (local)"


# Free-tier Gemini API quotas are per-minute; the council fires 4 calls at once,
# so retry 429s / transient 5xx with exponential backoff instead of failing.
RETRY = types.HttpRetryOptions(
    attempts=int(os.getenv("FITCHECK_RETRY_ATTEMPTS", "5")),
    initial_delay=2.0, max_delay=30.0, exp_base=2.0, jitter=0.5,
    http_status_codes=[408, 429, 500, 502, 503, 504],
)


class _SafeGemma3(Gemma):
    """ADK's Gemma-3 adapter drops the system instruction when a request has no
    user content yet; make sure there is always something to attach it to."""

    async def _preprocess_request(self, llm_request: LlmRequest) -> None:
        if not llm_request.contents:
            llm_request.contents = [types.Content(role="user", parts=[types.Part(text="Begin.")])]
        return await super()._preprocess_request(llm_request)


def build_model(model_id: str):
    if model_id.startswith("gemma-3"):
        return _SafeGemma3(model=model_id, retry_options=RETRY)
    if is_hosted(model_id):
        return Gemini(model=model_id, retry_options=RETRY)
    return LiteLlm(model=model_id)


def generation_config(model_id: str, temperature: float) -> types.GenerateContentConfig:
    cfg = types.GenerateContentConfig(
        temperature=temperature,
        # Generous: on thinking-capable models, reasoning tokens share this budget.
        max_output_tokens=int(os.getenv("FITCHECK_MAX_TOKENS", "2048")),
    )
    level = os.getenv("FITCHECK_THINKING")  # e.g. "minimal" (fast) or "high"
    if level and model_id.startswith("gemma-4"):
        cfg.thinking_config = types.ThinkingConfig(thinking_level=level)
    return cfg
