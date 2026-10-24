"""ADK callbacks to stop local models (e.g. Gemma) from re-calling the same tool in a loop."""

from __future__ import annotations

from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

_MAX_PER_TOOL = 1
_MAX_TOTAL_PER_TURN = 6

# ADK session state did not reliably persist temp keys between tool rounds with Ollama.
# In-process guard: (session_id, invocation_id, tool_name) -> count / cached result.
_TURN_TOOL_COUNT: dict[tuple[str, str, str], int] = {}
_TURN_TOOL_CACHE: dict[tuple[str, str, str], Any] = {}
_TURN_TOTAL: dict[tuple[str, str], int] = {}


def _session_id(tool_context: ToolContext) -> str:
    sess = getattr(tool_context, "session", None)
    return str(getattr(sess, "id", None) or "default")


def _invocation_id(tool_context: ToolContext) -> str:
    inv = getattr(tool_context, "invocation_id", None)
    if inv:
        return str(inv)
    try:
        ic = tool_context.get_invocation_context()
        return str(getattr(ic, "invocation_id", None) or "default")
    except Exception:
        return "default"


def _tool_key(tool_context: ToolContext, tool_name: str) -> tuple[str, str, str]:
    return (_session_id(tool_context), _invocation_id(tool_context), tool_name)


def _turn_key(tool_context: ToolContext) -> tuple[str, str]:
    return (_session_id(tool_context), _invocation_id(tool_context))


def before_agent_callback(callback_context: CallbackContext) -> None:
    """Reset per-turn counters when a new agent invocation starts (one user message)."""
    sid = str(getattr(callback_context.session, "id", None) or "default")
    inv = str(getattr(callback_context, "invocation_id", None) or "default")
    turn = (sid, inv)
    _TURN_TOTAL[turn] = 0
    to_drop = [k for k in _TURN_TOOL_COUNT if k[0] == sid and k[1] == inv]
    for k in to_drop:
        _TURN_TOOL_COUNT.pop(k, None)
        _TURN_TOOL_CACHE.pop(k, None)


def before_tool_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
) -> dict[str, Any] | None:
    """Block duplicate tool calls in one invocation (returns cached result + stop hint)."""
    name = tool.name
    tk = _tool_key(tool_context, name)
    turn = _turn_key(tool_context)

    if _TURN_TOOL_COUNT.get(tk, 0) >= _MAX_PER_TOOL:
        return {
            "duplicate_call_blocked": True,
            "tool": name,
            "instruction_to_model": (
                "FINAL ANSWER REQUIRED. You already have this tool's output in previous_result. "
                "Do NOT call any more tools. Reply to the user in plain text now."
            ),
            "previous_result": _TURN_TOOL_CACHE.get(tk),
        }

    total = _TURN_TOTAL.get(turn, 0)
    if total >= _MAX_TOTAL_PER_TURN:
        return {
            "tool_budget_exceeded": True,
            "instruction_to_model": (
                "FINAL ANSWER REQUIRED. Tool limit reached. Summarize for the user without more tools."
            ),
        }

    _TURN_TOOL_COUNT[tk] = _TURN_TOOL_COUNT.get(tk, 0) + 1
    _TURN_TOTAL[turn] = total + 1

    # Mirror to session state when supported (Gemini / future ADK)
    try:
        state = tool_context.state
        counts_key = f"temp:rentrakshak:counts:{turn[0]}:{turn[1]}"
        counts = dict(state.get(counts_key) or {})
        counts[name] = counts.get(name, 0) + 1
        state[counts_key] = counts
    except Exception:
        pass

    return None


def after_tool_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict[str, Any],
) -> dict[str, Any] | None:
    tk = _tool_key(tool_context, tool.name)
    enriched = dict(tool_response) if isinstance(tool_response, dict) else {"result": tool_response}
    enriched.setdefault(
        "agent_note",
        "Tool finished. Prefer a final text reply to the user; do not call this tool again.",
    )
    _TURN_TOOL_CACHE[tk] = enriched
    try:
        cache_key = f"temp:rentrakshak:cache:{tk[0]}:{tk[1]}:{tool.name}"
        tool_context.state[cache_key] = enriched
    except Exception:
        pass
    return enriched
