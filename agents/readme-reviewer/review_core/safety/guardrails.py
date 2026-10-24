"""Runtime guardrails applied to every tool call the agents make."""

import os
from collections import defaultdict

MAX_CALLS = int(os.getenv("MAX_TOOL_CALLS", "12"))
MAX_ARG_CHARS = 500
_MAX_TRACKED_RUNS = 1000

_calls = defaultdict(int)


def limit_tool_calls(tool, args, tool_context):
    """ADK ``before_tool_callback``: cap calls per agent per run and reject oversized arguments.

    Returning a dict skips the real tool and hands that dict to the model instead.
    """
    for value in args.values():
        if isinstance(value, str) and len(value) > MAX_ARG_CHARS:
            return {"error": f"Argument too long (limit {MAX_ARG_CHARS} characters). Call refused."}
    key = (
        getattr(tool_context, "invocation_id", ""),
        getattr(tool_context, "agent_name", ""),
    )
    if key not in _calls and len(_calls) >= _MAX_TRACKED_RUNS:
        _calls.pop(next(iter(_calls)))
    _calls[key] += 1
    if _calls[key] > MAX_CALLS:
        return {"error": "Tool call limit reached. Write the report using the results you already have."}
    return None
