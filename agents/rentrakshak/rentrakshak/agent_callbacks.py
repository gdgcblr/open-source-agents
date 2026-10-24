"""ADK callbacks to stop local models (e.g. Gemma) from re-calling the same tool in a loop."""

from __future__ import annotations

from typing import Any

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

_MAX_PER_TOOL = 1
_MAX_TOTAL_TOOLS = 8


def _counts_key(tool_context: ToolContext) -> str:
    inv = getattr(tool_context, "invocation_id", None) or "default"
    return f"temp:rentrakshak:tool_call_counts:{inv}"


def _cache_key(tool_context: ToolContext, tool_name: str) -> str:
    inv = getattr(tool_context, "invocation_id", None) or "default"
    return f"temp:rentrakshak:tool_cache:{inv}:{tool_name}"


def before_tool_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
) -> dict[str, Any] | None:
    """Block duplicate tool calls in one invocation (returns cached result + stop hint)."""
    state = tool_context.state
    counts_key = _counts_key(tool_context)
    counts: dict[str, int] = dict(state.get(counts_key) or {})
    name = tool.name

    if counts.get(name, 0) >= _MAX_PER_TOOL:
        return {
            "duplicate_call_blocked": True,
            "tool": name,
            "instruction_to_model": (
                "STOP. You already called this tool. Use previous_result and answer the user "
                "in plain text. Do not call this tool again unless the user sends a new message."
            ),
            "previous_result": state.get(_cache_key(tool_context, name)),
        }

    total = sum(counts.values())
    if total >= _MAX_TOTAL_TOOLS:
        return {
            "tool_budget_exceeded": True,
            "instruction_to_model": (
                "Maximum tool calls for this turn reached. Summarize results for the user now "
                "without calling more tools."
            ),
        }

    counts[name] = counts.get(name, 0) + 1
    state[counts_key] = counts
    return None


def after_tool_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict[str, Any],
) -> dict[str, Any] | None:
    tool_context.state[_cache_key(tool_context, tool.name)] = tool_response
    return None
