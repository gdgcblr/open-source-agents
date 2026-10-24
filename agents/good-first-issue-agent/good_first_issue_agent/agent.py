"""Optional Google ADK + Gemini layer.

Verified against google-adk 2.13.0 (google-genai 2.33.0):
  from google.adk import Agent
  from google.adk.runners import InMemoryRunner
  Agent(name=, model=, instruction=, tools=, generate_content_config=,
        before_model_callback=, before_tool_callback=, after_tool_callback=)

Guardrails enforced here (in code, not just in the prompt):
- Tool allowlist: only the read-only tools defined below can run.
- Tools are bound to the target repository/project; the model cannot choose another one.
- Tool arguments are validated (issue ids must be among the fetched candidates; paths must be
  relative with no '..', and secret-like files are refused).
- Budgets: at most MAX_TOOL_CALLS tool calls and MAX_MODEL_CALLS model calls per run.
- Every tool result is masked for secrets/personal data and truncated before the model sees it.
- The final answer is checked: unknown issue numbers and file paths are marked [unverified].
- A wall-clock timeout bounds the whole run.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from .errors import AgentError, AIUnavailableError
from .guardrails import check_model_output, clean, extract_paths, is_safe_repo_path, redact, wrap_untrusted
from .models import AIResult, Report
from .prompts import build_user_message, system_instruction

MAX_TOOL_CALLS = 6
MAX_MODEL_CALLS = 8
RUN_TIMEOUT = 60.0  # per attempt; at most two attempts (see FALLBACK_MODEL)
REQUEST_TIMEOUT_MS = 40_000  # one HTTP request to Gemini
REQUEST_ATTEMPTS = 2  # the SDK otherwise retries overloads with long back-off
# Used once, automatically, when the chosen model is overloaded (HTTP 503).
FALLBACK_MODEL = "gemini-flash-lite-latest"
APP_NAME = "good_first_issue_agent"
SECRET_FILE = re.compile(r"(?i)(^|/)(\.env(\..*)?|.*\.(pem|key|p12|pfx)|id_rsa.*|credentials\.json|service-account.*\.json|\.npmrc|\.pypirc)$")


@dataclass
class GuardState:
    allowed_tools: set[str]
    allowed_issue_ids: set[str]
    max_tool_calls: int = MAX_TOOL_CALLS
    max_model_calls: int = MAX_MODEL_CALLS
    tool_calls: int = 0
    model_calls: int = 0
    blocked: list[str] = field(default_factory=list)
    evidence_paths: set[str] = field(default_factory=set)


# ----------------------------------------------------------------------------
# Tools (closures bound to one repository / project; read-only)
# ----------------------------------------------------------------------------
def make_github_tools(client: Any, state: GuardState) -> list:
    def get_issue_comments(issue_number: int) -> dict:
        """Read up to 10 comments on one of the candidate issues in this repository.

        Args:
            issue_number: The issue number, e.g. 123. Must be one of the candidate issues.
        """
        try:
            comments = client.list_comments(int(issue_number), max_comments=10)
        except AgentError as exc:
            return {"error": str(exc)}
        items = []
        for c in comments:
            body = clean(c["body"], 1200)
            state.evidence_paths.update(extract_paths(body))
            items.append(f"[{c['author']} ({c['author_association'] or 'user'}), {c['created_at']}]\n{body}")
        text = "\n\n".join(items) or "(no comments)"
        return {"issue_number": int(issue_number), "comments": wrap_untrusted("issue-comments", text)}

    def list_repository_files(path: str = "") -> dict:
        """List files and folders at a path in this repository (default: the top level).

        Args:
            path: A relative directory path such as "docs" or "src/app". Empty for the top level.
        """
        try:
            entries = client.list_dir(path)
        except AgentError as exc:
            return {"error": str(exc)}
        for e in entries:
            if e.get("path"):
                state.evidence_paths.add(e["path"])
        return {"path": path or "/", "entries": [f"{e['path']} ({e['type']})" for e in entries]}

    def read_repository_file(path: str) -> dict:
        """Read the first 6,000 characters of a text file in this repository, such as CONTRIBUTING.md.

        Args:
            path: A relative file path such as "CONTRIBUTING.md" or "src/app/views.py".
        """
        try:
            text = client.read_file(path, max_chars=6000)
        except AgentError as exc:
            return {"error": str(exc)}
        state.evidence_paths.add(path.strip("/"))
        return {"path": path, "content": wrap_untrusted("repository-file", clean(text, 6000))}

    return [get_issue_comments, list_repository_files, read_repository_file]


def make_tracker_tools(client: Any, state: GuardState) -> list:
    def get_latest_stack_trace(issue_id: str) -> dict:
        """Get exception types, messages and stack frames (file, function, line) from the latest
        event of one of the candidate error-tracker issues. Local variables and user data are not included.

        Args:
            issue_id: The numeric issue id. Must be one of the candidate issues.
        """
        try:
            event = client.get_latest_event(str(issue_id))
        except AgentError as exc:
            return {"error": str(exc)}
        for fr in event.get("frames", []):
            if fr.get("file"):
                state.evidence_paths.add(fr["file"])
        return {"issue_id": str(issue_id), "event": wrap_untrusted("stack-trace", str(event))}

    return [get_latest_stack_trace]


# ----------------------------------------------------------------------------
# Guardrail callbacks
# ----------------------------------------------------------------------------
def _deep_redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)[0]
    if isinstance(value, list):
        return [_deep_redact(v) for v in value]
    if isinstance(value, dict):
        return {k: _deep_redact(v) for k, v in value.items()}
    return value


def make_callbacks(state: GuardState):
    def before_tool(tool: Any, args: dict[str, Any], tool_context: Any) -> dict | None:
        name = getattr(tool, "name", "")
        if name not in state.allowed_tools:
            state.blocked.append(f"tool '{name}' is not allowed")
            return {"error": f"Tool '{name}' is not allowed. Only read-only tools may be used."}
        if state.tool_calls >= state.max_tool_calls:
            state.blocked.append("tool-call budget exhausted")
            return {"error": "Tool-call budget exhausted. Answer now with the information you have."}

        for key in ("issue_number", "issue_id"):
            if key in args:
                value = str(args[key]).lstrip("#").strip()
                if value not in state.allowed_issue_ids:
                    state.blocked.append(f"{name} for non-candidate issue {value}")
                    return {"error": f"Issue {value} is not one of the fetched candidates. Allowed: "
                                     + ", ".join(sorted(state.allowed_issue_ids)[:10])}
                args[key] = int(value) if key == "issue_number" else value
        if "path" in args:
            path = str(args.get("path") or "")
            if not is_safe_repo_path(path):
                state.blocked.append(f"unsafe path '{path[:60]}'")
                return {"error": "Invalid path. Use a relative path inside the repository without '..'."}
            if SECRET_FILE.search(path.strip("/")):
                state.blocked.append(f"secret-like file '{path[:60]}'")
                return {"error": "Reading credential or environment files is not allowed."}
        state.tool_calls += 1
        return None

    def after_tool(tool: Any, args: dict[str, Any], tool_context: Any, tool_response: Any) -> dict | None:
        if isinstance(tool_response, dict):
            return _deep_redact(tool_response)
        return None

    def before_model(callback_context: Any, llm_request: Any) -> Any:
        state.model_calls += 1
        if state.model_calls > state.max_model_calls:
            from google.adk.models.llm_response import LlmResponse
            from google.genai import types

            state.blocked.append("model-call budget exhausted")
            return LlmResponse(content=types.Content(
                role="model",
                parts=[types.Part(text="Stopped: the model-call limit for this run was reached.")],
            ))
        return None

    return before_tool, after_tool, before_model


# ----------------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------------
def _is_real(value: str | None) -> bool:
    v = (value or "").strip().lower()
    return bool(v) and not v.startswith("your_") and not v.endswith("_here")


def _has_credentials() -> bool:
    if _is_real(os.environ.get("GOOGLE_API_KEY")) or _is_real(os.environ.get("GEMINI_API_KEY")):
        return True
    vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes")
    return vertex and bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))


class _Overloaded(AIUnavailableError):
    """The model is temporarily overloaded (HTTP 503); worth one retry on another model."""


def _is_overloaded(msg: str) -> bool:
    low = msg.lower()
    return any(k in low for k in ("503", "504", "unavailable", "overloaded", "high demand", "deadline"))


def _friendly_model_error(exc: Exception) -> str:
    msg = redact(str(exc))[0]
    low = msg.lower()
    if _is_overloaded(msg):
        return "Gemini is overloaded right now (503/504); try again in a minute or set GEMINI_MODEL to another model"
    if "429" in msg or "resource_exhausted" in low or "quota" in low:
        return "Gemini quota or rate limit exceeded; try again later or check your plan"
    if "api key not valid" in low or "api_key_invalid" in low or "401" in msg or "permission_denied" in low:
        return "Gemini rejected the API key; check GOOGLE_API_KEY"
    if "not found" in low and "model" in low:
        return "the configured Gemini model was not found; set GEMINI_MODEL to a supported model"
    return f"model call failed ({type(exc).__name__}: {msg[:160]})"


def run_ai_analysis(
    *,
    report: Report,
    ctx: dict[str, Any],
    model: Any,
    timeout: float = RUN_TIMEOUT,
) -> AIResult:
    """Run the ADK agent for report.selected. `model` is a Gemini model name, or a
    google.adk BaseLlm instance (used by tests to run offline)."""
    if isinstance(model, str) and not _has_credentials():
        raise AIUnavailableError("no GOOGLE_API_KEY set; see .env.example")
    try:
        from google.adk import Agent
        from google.adk.runners import InMemoryRunner
        from google.genai import types
    except ImportError:
        raise AIUnavailableError("google-adk is not installed; run pip install -r requirements.txt")
    # ADK logs model failures with full tracebacks; we report them as one clean warning instead.
    for name in ("google_adk", "google.adk", "google_genai", "google.genai"):
        logging.getLogger(name).setLevel(logging.CRITICAL)

    sel = report.selected
    if sel is None:
        raise AIUnavailableError("no issue selected")

    candidate_ids = {s.issue.id for s in report.ranked} | {sel.issue.id}
    state = GuardState(
        allowed_tools=set(), allowed_issue_ids=candidate_ids,
        max_tool_calls=MAX_TOOL_CALLS, max_model_calls=MAX_MODEL_CALLS,
    )
    if "github" in ctx:
        tools = make_github_tools(ctx["github"], state)
        meta = ctx.get("meta") or {}
        repo_context = f"Description: {meta.get('description', '')}\nMain language: {meta.get('language', '')}"
    else:
        tools = make_tracker_tools(ctx["tracker"], state)
        repo_context = ""
    state.allowed_tools = {t.__name__ for t in tools}
    for s in report.ranked or [sel]:
        state.evidence_paths.update(s.evidence_paths)

    before_tool, after_tool, before_model = make_callbacks(state)
    message = build_user_message(report, repo_context)

    def _attempt(model_to_use: Any) -> str:
        agent = Agent(
            name="good_first_issue_agent",
            model=model_to_use,
            instruction=system_instruction(MAX_TOOL_CALLS, report.source),
            tools=tools,
            generate_content_config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=2048,
                http_options=types.HttpOptions(
                    timeout=REQUEST_TIMEOUT_MS,
                    retry_options=types.HttpRetryOptions(attempts=REQUEST_ATTEMPTS),
                ),
            ),
            before_model_callback=before_model,
            before_tool_callback=before_tool,
            after_tool_callback=after_tool,
        )

        async def _run() -> str:
            runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
            try:
                session = await runner.session_service.create_session(app_name=APP_NAME, user_id="local-user")
                final = ""
                async for event in runner.run_async(
                    user_id="local-user",
                    session_id=session.id,
                    new_message=types.Content(role="user", parts=[types.Part(text=message)]),
                ):
                    if getattr(event, "error_message", None):
                        raise RuntimeError(event.error_message)
                    if event.is_final_response() and event.content and event.content.parts:
                        text = "".join(p.text or "" for p in event.content.parts if getattr(p, "text", None))
                        if text.strip():
                            final = text
                return final
            finally:
                await runner.close()

        try:
            return asyncio.run(asyncio.wait_for(_run(), timeout=timeout))
        except asyncio.TimeoutError:
            # A slow model is usually an overloaded one; allow the fallback model to try.
            raise _Overloaded(f"the model did not finish within {timeout:g}s")
        except (AIUnavailableError, AgentError):
            raise
        except Exception as exc:  # network, auth, quota, overload, SDK errors
            friendly = _friendly_model_error(exc)
            if _is_overloaded(str(exc)):
                raise _Overloaded(friendly)
            raise AIUnavailableError(friendly)

    used_model = model
    notes: list[str] = []
    try:
        text = _attempt(model)
    except _Overloaded:
        if not isinstance(model, str) or model == FALLBACK_MODEL:
            raise
        # One retry on a lighter model, with fresh budgets.
        state.tool_calls = state.model_calls = 0
        state.blocked.clear()
        used_model = FALLBACK_MODEL
        notes.append(f"{model} was overloaded or too slow; this answer comes from {FALLBACK_MODEL}.")
        text = _attempt(FALLBACK_MODEL)

    if not text.strip():
        raise AIUnavailableError("the model returned an empty answer")

    checked = check_model_output(
        text,
        known_issue_ids=candidate_ids,
        evidence_paths=state.evidence_paths,
        check_issue_refs=report.source == "github",
    )
    warnings = notes + list(checked.warnings)
    if state.blocked:
        warnings.append("Guardrails blocked: " + "; ".join(dict.fromkeys(state.blocked)))
    return AIResult(
        text=checked.text,
        model=used_model if isinstance(used_model, str) else getattr(used_model, "model", type(used_model).__name__),
        warnings=warnings,
        tool_calls=state.tool_calls,
    )
