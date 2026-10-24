"""Tool guardrails. ADK passes callback args by keyword, so names must match exactly."""
import json
import re
from pathlib import Path

from .tools import jail_path  # also puts the project root on sys.path
from checks import redact  # noqa: E402

MAX_CALLS = 12
ALLOWED = {"python", "pip", "pytest", "uv", "npm", "node"}
SYMBOLS = [";", "&", "|", ">", "<", "`", "$(", "Invoke-"]
WORDS = re.compile(r"\b(rm|del|rmdir|curl|wget|sudo|powershell|format|iex)\b", re.IGNORECASE)


def command_problem(command: str) -> str | None:
    tokens = (command or "").split()
    if not tokens:
        return "empty command"
    if tokens[0].lower() not in ALLOWED:
        return f"'{tokens[0]}' is not an allowed program ({', '.join(sorted(ALLOWED))})"
    for sym in SYMBOLS:
        if sym in command:
            return f"forbidden character/sequence '{sym}'"
    m = WORDS.search(command)
    if m:
        return f"forbidden word '{m.group()}'"
    return None


def _block(tool, args, tool_context, reason: str) -> dict:
    entry = {"tool": tool.name, "args": redact(json.dumps(args, default=str)), "reason": reason}
    tool_context.state["blocked"] = list(tool_context.state.get("blocked", [])) + [entry]
    return {"blocked": True, "reason": reason}


def before_tool_callback(tool, args, tool_context):
    state = tool_context.state
    state["calls"] = state.get("calls", 0) + 1
    if state["calls"] > MAX_CALLS:
        return _block(tool, args, tool_context, f"tool-call budget of {MAX_CALLS} exceeded")
    reason = None
    if tool.name == "run_command":
        reason = command_problem(args.get("command", ""))
    elif tool.name == "read_file":
        if jail_path(Path(state["sandbox"]), args.get("path", "")) is None:
            reason = "path escapes the project sandbox"
    return _block(tool, args, tool_context, reason) if reason else None


def _redact_any(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: _redact_any(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_any(v) for v in value]
    return value


def after_tool_callback(tool, args, tool_context, tool_response):
    clean = _redact_any(tool_response)
    if not isinstance(clean, dict):
        clean = {"result": clean}
    state = tool_context.state
    if tool.name == "run_command" and "exit_code" in clean:
        run = {"command": redact(args.get("command", "")), "exit_code": clean["exit_code"]}
        state["runs"] = list(state.get("runs", [])) + [run]
    log = json.dumps({"tool": tool.name, "response": clean}, default=str)
    state["tool_log"] = list(state.get("tool_log", [])) + [log]
    return clean
