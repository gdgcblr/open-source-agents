"""The full request pipeline shared by the CLI and the HTTP server.

input guardrails -> ADK agent -> output guardrails -> Deck
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from . import guardrails
from .config import MAX_LLM_CALLS, RETRY_LLM_CALLS, load_settings
from .deck import Deck, Draft, DraftError, build_deck, parse_draft
from .duration import format_seconds
from .prompts import JSON_ONLY_REMINDER, build_request

APP_NAME = "glasses_speaker_cue_agent"
USER_ID = "local"

Progress = Callable[[str], None]


class UpstreamError(RuntimeError):
    """The model call failed or returned nothing usable.

    `kind` is one of: rate_limited, auth, model, network, error.
    """

    def __init__(self, message: str, kind: str = "error") -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class CueRequest:
    notes: str
    minutes: float
    language: str = "en"
    include_qa: bool = True
    image: bytes | None = None
    keep_pii: bool = False


def quiet_sdk_logs() -> None:
    """ADK logs full tracebacks for API errors; callers report one clear line instead."""
    for name in ("google_adk", "google_genai"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def friendly_api_error(code: object, message: str) -> UpstreamError:
    """One actionable line for common Gemini failures instead of raw JSON."""
    text = f"{code} {message}"
    if "API_KEY_INVALID" in text or "API key not valid" in text:
        return UpstreamError(
            "Gemini rejected the API key. Check GOOGLE_API_KEY in .env: it should be a key "
            "from https://aistudio.google.com/apikey",
            "auth",
        )
    if "429" in text or "RESOURCE_EXHAUSTED" in text:
        return UpstreamError(
            "Gemini rate limit or quota reached. Wait a minute and try again.", "rate_limited"
        )
    if "UNAVAILABLE" in text or "503" in text:
        return UpstreamError(
            "Gemini is temporarily overloaded. Try again in a minute.", "rate_limited"
        )
    if "PERMISSION_DENIED" in text or "403" in text:
        return UpstreamError(
            "Gemini denied access for this key. Check that the Gemini API is enabled for it.",
            "auth",
        )
    if "NOT_FOUND" in text or "404" in text:
        return UpstreamError(
            "Model not found. Set MODEL_NAME in .env to a Gemini model your key can use.", "model"
        )
    return UpstreamError(f"Gemini API error ({code}). Run with --verbose for details.")


def _describe(response: dict) -> str:
    fits = response.get("fits")
    change = response.get("word_change_needed", 0)
    hint = "" if fits else f", {'add' if change > 0 else 'cut'} ~{abs(change)} words"
    return (
        f"{response.get('measured')} vs target {format_seconds(response.get('target_seconds', 0))}"
        f" -> {'fits' if fits else 'outside target'}{hint}"
    )


@dataclass
class _Turn:
    text: str = ""
    checks: int = 0


async def _run_turn(
    runner, session_id: str, content, progress: Progress, max_llm_calls: int, turn: _Turn
) -> None:
    from google.adk.agents import RunConfig

    turn.text = ""
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=content,
        run_config=RunConfig(max_llm_calls=max_llm_calls),
    ):
        if event.error_code:
            raise friendly_api_error(event.error_code, event.error_message or "")
        for resp in event.get_function_responses():
            if resp.name == "estimate_speaking_time" and isinstance(resp.response, dict):
                turn.checks += 1
                progress(f"  [time check {turn.checks}] {_describe(resp.response)}")
        if event.is_final_response() and event.content and event.content.parts:
            turn.text = "".join(p.text for p in event.content.parts if p.text and not p.thought)


async def run_agent(
    request: str, image: tuple[bytes, str] | None, model: str, progress: Progress
) -> Draft:
    """Runs the agent and returns its parsed draft, asking once more if it is not valid JSON.

    Both turns share one session, so the revision counter carries over, and
    together they stay within MAX_LLM_CALLS.
    """
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from .agent import root_agent

    # The module-level agent reads MODEL_NAME at import time, possibly before
    # .env was loaded; the settings value is authoritative.
    agent = root_agent.clone(update={"model": model})
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name=APP_NAME, user_id=USER_ID)
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=sessions)

    parts = [types.Part(text=request)]
    if image:
        parts.append(types.Part.from_bytes(data=image[0], mime_type=image[1]))

    turn = _Turn()
    first_turn_calls = MAX_LLM_CALLS - RETRY_LLM_CALLS
    content = types.Content(role="user", parts=parts)
    await _run_turn(runner, session.id, content, progress, first_turn_calls, turn)
    try:
        return parse_draft(turn.text)
    except DraftError:
        if not turn.text.strip():
            raise UpstreamError(
                "The model returned no text (it may have been blocked by safety)."
            ) from None
        progress("  Reply was not valid JSON; asking once more.")
    reminder = types.Content(role="user", parts=[types.Part(text=JSON_ONLY_REMINDER)])
    await _run_turn(runner, session.id, reminder, progress, RETRY_LLM_CALLS, turn)
    return parse_draft(turn.text)


def _as_upstream_error(exc: Exception) -> UpstreamError | None:
    """Maps SDK and network failures to UpstreamError; None for anything unexpected."""
    import httpx
    from google.adk.agents.invocation_context import LlmCallsLimitExceededError
    from google.genai import errors

    if isinstance(exc, LlmCallsLimitExceededError):
        return UpstreamError("The agent hit its model-call limit before finishing.")
    if isinstance(exc, errors.APIError):
        return friendly_api_error(exc.code, str(exc))
    network_errors: tuple[type[BaseException], ...] = (httpx.TransportError, ConnectionError)
    try:
        import aiohttp

        network_errors += (aiohttp.ClientError,)
    except ImportError:
        pass
    if isinstance(exc, network_errors):
        return UpstreamError("Could not reach Gemini. Check your internet connection.", "network")
    return None


async def create_deck(req: CueRequest, progress: Progress = lambda _: None) -> Deck:
    """Validates the request, runs the agent and returns a checked deck.

    Raises InputError, BlockedError or ConfigError before anything is sent to
    the model, and DraftError or UpstreamError if the model call fails.
    """
    notes = guardrails.validate_notes(req.notes)
    target_seconds = guardrails.validate_minutes(req.minutes)
    language = guardrails.validate_language(req.language)
    image = (req.image, guardrails.validate_image(req.image)) if req.image else None
    guardrails.block_secrets(notes)
    if not req.keep_pii:
        notes, redacted = guardrails.redact_pii(notes)
        if any(redacted.values()):
            progress(
                f"Redacted before sending: {redacted['email']} email(s), "
                f"{redacted['phone']} phone(s)."
            )

    settings = load_settings()
    progress(
        f"Writing a {format_seconds(target_seconds)} {language} script with {settings.model}..."
    )

    request = build_request(
        guardrails.fence_notes(notes),
        target_seconds,
        language,
        include_qa=req.include_qa,
        has_slide=image is not None,
    )
    try:
        draft = await run_agent(request, image, settings.model, progress)
    except (UpstreamError, DraftError):
        raise
    except Exception as exc:
        mapped = _as_upstream_error(exc)
        if mapped is None:
            raise
        raise mapped from exc

    deck = build_deck(draft, target_seconds, language, include_qa=req.include_qa)
    return guardrails.check_grounding(deck, notes, has_slide=image is not None)
