"""Provider abstraction.

Two providers are supported:

* ``mock``   - fully offline, deterministic heuristic (default). stdlib only.
* ``openai`` - OpenAI chat completions, used only when an API key is present.
               The ``openai`` package is imported lazily so the default path
               never needs it installed.

Auto-selection: if an ``OPENAI_API_KEY`` is set *and* the ``openai`` package
imports, ``auto`` resolves to ``openai``; otherwise it resolves to ``mock``.
An explicit provider (CLI flag or ``PROVIDER`` env var) always wins.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Mapping, Optional

from .diff_parser import parse_diff
from .message_builder import build_message, render

VALID_PROVIDERS = ("auto", "mock", "openai")
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class ProviderError(Exception):
    """Raised for a friendly, handled provider/config failure."""


class Provider:
    """Common interface. ``generate`` returns the commit message text."""

    name = "base"

    def generate(self, diff_text: str, model: Optional[str] = None, no_body: bool = False) -> str:  # noqa: D401
        raise NotImplementedError


class MockProvider(Provider):
    """Offline heuristic provider. Never touches the network."""

    name = "mock"

    def generate(self, diff_text: str, model: Optional[str] = None, no_body: bool = False) -> str:
        summary = parse_diff(diff_text)
        if summary.is_empty():
            # Nothing parseable: still return a valid, honest message.
            return "chore: update repository"
        message = build_message(summary, no_body=no_body)
        return render(message)


class OpenAIProvider(Provider):
    """OpenAI-backed provider. The SDK is imported only when used."""

    name = "openai"

    def generate(self, diff_text: str, model: Optional[str] = None, no_body: bool = False) -> str:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ProviderError(
                "The 'openai' provider needs OPENAI_API_KEY. Set it in your "
                "environment or run with --provider mock for offline use."
            )
        if not _module_available("openai"):
            raise ProviderError(
                "The 'openai' package is not installed. Run 'pip install openai' "
                "or use --provider mock for offline use."
            )

        # Lazy import: only reached when the key and package are both present.
        import openai  # noqa: PLC0415

        model_name = model or os.environ.get("MODEL_NAME") or DEFAULT_OPENAI_MODEL
        prompt = _build_prompt(diff_text, no_body=no_body)
        try:
            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            content = response.choices[0].message.content or ""
        except Exception as exc:  # pragma: no cover - needs real network
            raise ProviderError(f"OpenAI request failed: {exc}") from exc
        return content.strip()


_SYSTEM_PROMPT = (
    "You are an assistant that writes Conventional Commits messages. Reply with "
    "only the commit message: a header line 'type(scope): summary' using one of "
    "feat, fix, docs, refactor, test, chore, optionally followed by a blank line "
    "and bullet-point body. No prose, no code fences."
)


def _build_prompt(diff_text: str, no_body: bool) -> str:
    body_note = (
        "Do not include a body; return only the header line."
        if no_body
        else "Include a short bullet-point body summarising the changes."
    )
    return (
        "Write a Conventional Commits message for the following staged git diff.\n"
        f"{body_note}\n\n"
        "```diff\n"
        f"{diff_text}\n"
        "```"
    )


def _module_available(name: str) -> bool:
    """True if ``name`` can be imported without importing it."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):  # pragma: no cover - defensive
        return False


def resolve_provider(cli_flag: Optional[str], env: Mapping[str, str]) -> str:
    """Resolve the concrete provider name from flag, env, and key presence."""
    chosen = cli_flag or env.get("PROVIDER") or "auto"
    chosen = chosen.lower()
    if chosen not in VALID_PROVIDERS:
        raise ProviderError(
            f"Unknown provider '{chosen}'. Choose from: {', '.join(VALID_PROVIDERS)}."
        )
    if chosen == "auto":
        if env.get("OPENAI_API_KEY") and _module_available("openai"):
            return "openai"
        return "mock"
    return chosen


def get_provider(name: str) -> Provider:
    """Instantiate a concrete provider by resolved name."""
    if name == "mock":
        return MockProvider()
    if name == "openai":
        return OpenAIProvider()
    raise ProviderError(f"Unsupported provider '{name}'.")
