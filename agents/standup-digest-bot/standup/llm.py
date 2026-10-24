"""Pluggable LLM providers.

The agent needs a text-in/text-out chat model, but we never want to hard-code a
single vendor. This module exposes one tiny interface (``LLMProvider.complete``)
and four implementations:

* ``ollama`` (default) - fully local, no API key. Addresses the "build locally"
  requirement.
* ``gemini`` / ``openai`` - optional hosted providers, used only if selected and
  the matching key is present.
* ``mock`` - deterministic, dependency-free. Powers ``--test-mode`` so the agent
  and the eval harness are runnable on a clean machine with zero credentials.

The factory degrades gracefully: if a hosted/local provider is requested but its
dependency or key is missing, it raises a clear, actionable error rather than
failing deep inside a request.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Protocol

logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str:
        """Return the model's text response for a system+user prompt."""
        ...


# --------------------------------------------------------------------------- #
# Ollama (local default)
# --------------------------------------------------------------------------- #
class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str, base_url: str, timeout: int | None = None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        # Local CPU inference can be slow, especially on the first (cold) call
        # while weights load into memory. Make the read timeout configurable via
        # OLLAMA_TIMEOUT so larger models on modest hardware are not cut off.
        self.timeout = timeout or int(os.getenv("OLLAMA_TIMEOUT", "600"))

    def complete(self, system: str, user: str) -> str:
        import requests  # local import keeps mock/test path dependency-free

        resp = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "options": {"temperature": 0.2},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=self.timeout,
        )
        if resp.status_code == 404:
            raise RuntimeError(
                f"Ollama model '{self.model}' not found. Run: ollama pull {self.model}"
            )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


# --------------------------------------------------------------------------- #
# Gemini (optional)
# --------------------------------------------------------------------------- #
class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str, api_key: str):
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "google-generativeai not installed. "
                "Install extras: pip install .[gemini]"
            ) from exc
        genai.configure(api_key=api_key)
        self._genai = genai
        self.model = model

    def complete(self, system: str, user: str) -> str:
        model = self._genai.GenerativeModel(
            self.model, system_instruction=system
        )
        resp = model.generate_content(
            user, generation_config={"temperature": 0.2}
        )
        return resp.text


# --------------------------------------------------------------------------- #
# OpenAI (optional)
# --------------------------------------------------------------------------- #
class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str, api_key: str):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "openai not installed. Install extras: pip install .[openai]"
            ) from exc
        self._client = OpenAI(api_key=api_key)
        self.model = model

    def complete(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""


# --------------------------------------------------------------------------- #
# Mock (offline / deterministic)
# --------------------------------------------------------------------------- #
class MockProvider:
    """Deterministic provider that produces a grounded digest without any model.

    It parses the evidence block out of the user prompt and emits one bullet per
    event, always citing the event_id. This lets the full pipeline + evals run
    offline and gives reviewers reproducible output. It intentionally never
    invents work, so it also demonstrates the grounded-by-construction idea.
    """

    name = "mock"

    _EVIDENCE_RE = re.compile(r"^\s*(\[[^\]]+\])\s+(.*)$")

    def complete(self, system: str, user: str) -> str:
        lines = []
        in_evidence = False
        for raw in user.splitlines():
            if raw.strip().upper().startswith("EVIDENCE"):
                in_evidence = True
                continue
            if in_evidence:
                m = self._EVIDENCE_RE.match(raw)
                if m:
                    # Emit "[id] text" with no leading bullet marker; the agent
                    # owns bullet formatting and verifies the leading [id].
                    lines.append(f"{m.group(1)} {_tidy(m.group(2))}")
        if not lines:
            # No evidence -> say so honestly rather than fabricate.
            return json.dumps(
                {
                    "yesterday": [],
                    "today": ["[confirm: no tracked activity found - add plan]"],
                    "blockers": [],
                }
            )
        return json.dumps(
            {
                "yesterday": lines,
                "today": ["[confirm: add today's plan]"],
                "blockers": [],
            }
        )


def _tidy(text: str) -> str:
    # Turn "commit in owner/repo: fix bug" into "Fixed bug (owner/repo)" style
    # lightly; keep it simple and deterministic.
    return text.strip()


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
def get_provider(
    provider: str | None = None,
    model: str | None = None,
) -> LLMProvider:
    provider = (provider or os.getenv("LLM_PROVIDER") or "ollama").lower()
    model = model or os.getenv("LLM_MODEL") or _default_model(provider)

    if provider == "mock":
        return MockProvider()
    if provider == "ollama":
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return OllamaProvider(model=model, base_url=base)
    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            raise RuntimeError("LLM_PROVIDER=gemini but GEMINI_API_KEY is not set")
        return GeminiProvider(model=model, api_key=key)
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set")
        return OpenAIProvider(model=model, api_key=key)

    raise RuntimeError(
        f"Unknown LLM_PROVIDER '{provider}'. Use: ollama | gemini | openai | mock"
    )


def _default_model(provider: str) -> str:
    return {
        "ollama": "llama3.1",
        "gemini": "gemini-2.5-flash",
        "openai": "gpt-4o-mini",
        "mock": "mock",
    }.get(provider, "llama3.1")
