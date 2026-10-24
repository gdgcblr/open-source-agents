"""ADK callbacks: structured logging and loop/retry guards.

Pure Python (no ADK import) so the logic can be tested without ADK installed.

Guards (enforced here, not only requested in the prompt):
  * ``AGENT_MAX_TOOL_CALLS``: total tool calls allowed per user request.
  * ``AGENT_MAX_RETRIES``: how often an identical failing call may be repeated.
When a limit is hit the tool is not executed; the model receives a structured
failure explaining why, so it can stop and report.
"""

import json
import logging
from typing import Any, Dict, Optional

from .config import get_settings

LOGGER = logging.getLogger("android_agent")
STATE_KEY = "android_agent_budget"

BUDGET_EXCEEDED = "AGENT_TOOL_BUDGET_EXCEEDED"
RETRY_LIMIT = "AGENT_RETRY_LIMIT_REACHED"
_GUARD_CODES = (BUDGET_EXCEEDED, RETRY_LIMIT)
_TYPED_TEXT_TOOLS = {"input_text": ("text",), "type_text": ("text",)}


def configure_logging() -> None:
    """Attach a compact stderr handler once (ADK/`adk run` may configure its own)."""
    if LOGGER.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s", "%H:%M:%S"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(getattr(logging, get_settings().log_level, logging.INFO))
    LOGGER.propagate = False


def _log(event: str, **fields: Any) -> None:
    LOGGER.info(json.dumps({"event": event, **fields}, default=str, ensure_ascii=False))


def redact_args(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Hide text typed into the device unless AGENT_LOG_TYPED_TEXT is enabled."""
    if get_settings().log_typed_text:
        return dict(args)
    hidden = _TYPED_TEXT_TOOLS.get(tool_name, ())
    return {
        k: (f"<{len(str(v))} chars>" if k in hidden and v is not None else v)
        for k, v in args.items()
    }


def _signature(tool_name: str, args: Dict[str, Any]) -> str:
    return f"{tool_name}:{json.dumps(args, sort_keys=True, default=str)}"


def _budget(tool_context: Any) -> Dict[str, Any]:
    """Per-invocation counters, reset whenever a new user request starts."""
    invocation = getattr(tool_context, "invocation_id", None)
    budget = tool_context.state.get(STATE_KEY)
    if not isinstance(budget, dict) or budget.get("invocation") != invocation:
        budget = {"invocation": invocation, "calls": 0, "fail_streaks": {}}
    return budget


def _blocked(tool_name: str, code: str, details: str) -> Dict[str, Any]:
    return {
        "success": False,
        "action": tool_name,
        "message": "Call refused by the agent's safety limits; the action was NOT executed",
        "data": {},
        "error": {"code": code, "details": details},
        "agent_note": "Stop acting. Report the failure to the user using the failure format.",
    }


def before_tool_callback(tool: Any, args: Dict[str, Any], tool_context: Any) -> Optional[Dict[str, Any]]:
    """Log the call and enforce the tool-call and retry budgets."""
    settings = get_settings()
    name = getattr(tool, "name", str(tool))
    budget = _budget(tool_context)
    budget["calls"] += 1
    sig = _signature(name, args)
    streak = budget["fail_streaks"].get(sig, 0)

    refusal: Optional[Dict[str, Any]] = None
    if budget["calls"] > settings.max_tool_calls:
        refusal = _blocked(
            name, BUDGET_EXCEEDED,
            f"More than {settings.max_tool_calls} tool calls were used for this request.",
        )
    elif streak >= settings.max_retries + 1:
        refusal = _blocked(
            name, RETRY_LIMIT,
            f"The identical call already failed {streak} times "
            f"(limit: 1 attempt + {settings.max_retries} retries). Change approach or stop.",
        )

    tool_context.state[STATE_KEY] = budget
    _log(
        "tool_call" if refusal is None else "tool_refused",
        tool=name, call_no=budget["calls"], args=redact_args(name, args),
        **({"reason": refusal["error"]["code"]} if refusal else {}),
    )
    return refusal


def after_tool_callback(
    tool: Any, args: Dict[str, Any], tool_context: Any, tool_response: Any
) -> Optional[Dict[str, Any]]:
    """Log the result and track consecutive identical failures. Leaves the result unchanged."""
    name = getattr(tool, "name", str(tool))
    result = tool_response if isinstance(tool_response, dict) else {}
    error = result.get("error") or {}
    code = error.get("code")
    success = result.get("success")

    if code not in _GUARD_CODES:
        budget = _budget(tool_context)
        sig = _signature(name, args)
        if success is False:
            budget["fail_streaks"][sig] = budget["fail_streaks"].get(sig, 0) + 1
        else:
            budget["fail_streaks"].pop(sig, None)
        tool_context.state[STATE_KEY] = budget

    _log(
        "tool_result", tool=name, success=success, error_code=code,
        message=result.get("message"),
        **({"details": str(error.get("details"))[:200]} if error.get("details") else {}),
    )
    return None


def after_model_callback(callback_context: Any, llm_response: Any) -> None:
    """Log the model's visible reasoning/decision text (not tool arguments)."""
    try:
        parts = getattr(getattr(llm_response, "content", None), "parts", None) or []
        text = " ".join(
            p.text.strip() for p in parts if getattr(p, "text", None) and p.text.strip()
        )
        calls = [
            getattr(p.function_call, "name", None)
            for p in parts if getattr(p, "function_call", None)
        ]
        if text or calls:
            _log("agent_decision", text=text[:300] or None, next_tool_calls=calls or None)
    except Exception:  # noqa: BLE001 - logging must never break the run
        pass
    return None
