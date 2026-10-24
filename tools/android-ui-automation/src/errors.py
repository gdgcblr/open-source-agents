"""Exception types and the ``guarded`` decorator.

Internal code raises :class:`ToolError`; public tool methods are wrapped with
:func:`guarded` so callers always receive an :class:`ActionResponse` and never
an exception.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

from .models.responses import ActionResponse, ErrorCode

F = TypeVar("F", bound=Callable[..., Any])


class ToolError(Exception):
    """Base error carrying a machine-readable code."""

    def __init__(self, code: ErrorCode, message: str, details: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


class ADBError(ToolError):
    """Raised when an ADB invocation fails."""


def guarded(action: str) -> Callable[[F], F]:
    """Convert exceptions raised by a tool method into failure responses."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> ActionResponse:
            try:
                return fn(*args, **kwargs)
            except ToolError as exc:
                return ActionResponse.fail(action, exc.code, exc.message, exc.details)
            except Exception as exc:  # noqa: BLE001 - last-resort safety net
                return ActionResponse.fail(
                    action,
                    ErrorCode.UNEXPECTED_ERROR,
                    "Unexpected error",
                    f"{type(exc).__name__}: {exc}",
                )

        return wrapper  # type: ignore[return-value]

    return decorator
