
"""Trace-ID context shared by the pytest plugin and services."""
from contextvars import ContextVar, Token

_trace_id: ContextVar[str | None] = ContextVar(
    "ai_trace_id", default=None
)


def get_trace_id() -> str | None:
    return _trace_id.get()


def set_trace_id(trace_id: str) -> Token:
    return _trace_id.set(trace_id)


def reset_trace_id(token: Token) -> None:
    _trace_id.reset(token)
