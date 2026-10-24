"""Common structured response model returned by every tool action."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Union


class ErrorCode(str, Enum):
    """Machine-readable error codes."""

    ADB_NOT_FOUND = "ADB_NOT_FOUND"
    DEVICE_NOT_CONNECTED = "DEVICE_NOT_CONNECTED"
    MULTIPLE_DEVICES = "MULTIPLE_DEVICES"
    COMMAND_FAILED = "COMMAND_FAILED"
    COMMAND_TIMEOUT = "COMMAND_TIMEOUT"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    APP_LAUNCH_FAILED = "APP_LAUNCH_FAILED"
    APP_STOP_FAILED = "APP_STOP_FAILED"
    ELEMENT_NOT_FOUND = "ELEMENT_NOT_FOUND"
    ELEMENT_NOT_INTERACTABLE = "ELEMENT_NOT_INTERACTABLE"
    UI_HIERARCHY_UNAVAILABLE = "UI_HIERARCHY_UNAVAILABLE"
    EXPECTED_STATE_NOT_REACHED = "EXPECTED_STATE_NOT_REACHED"
    TEXT_VERIFICATION_FAILED = "TEXT_VERIFICATION_FAILED"
    DEVICE_UNRESPONSIVE = "DEVICE_UNRESPONSIVE"
    SCREENSHOT_FAILED = "SCREENSHOT_FAILED"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"


@dataclass
class ErrorInfo:
    code: str
    details: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {"code": self.code, "details": self.details}


@dataclass
class ActionResponse:
    """Result of a single action.

    ``success`` means the *intended* action succeeded (including any requested
    post-action verification), not merely that an ADB command ran.
    """

    success: bool
    action: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[ErrorInfo] = None

    # -- constructors -----------------------------------------------------
    @classmethod
    def ok(
        cls, action: str, message: str, data: Optional[Dict[str, Any]] = None
    ) -> "ActionResponse":
        return cls(success=True, action=action, message=message, data=data or {})

    @classmethod
    def fail(
        cls,
        action: str,
        code: Union[ErrorCode, str],
        message: str,
        details: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> "ActionResponse":
        code_str = code.value if isinstance(code, Enum) else str(code)
        return cls(
            success=False,
            action=action,
            message=message,
            data=data or {},
            error=ErrorInfo(code=code_str, details=details),
        )

    # -- serialisation ----------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "success": self.success,
            "action": self.action,
            "message": self.message,
            "data": self.data,
        }
        if self.error is not None:
            result["error"] = self.error.to_dict()
        return result

    def to_json(self, indent: Optional[int] = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, default=str)

    def summary(self) -> str:
        """Short human-readable one/two-liner, e.g. ``✓ click: Element clicked``."""
        mark = "✓" if self.success else "✗"
        line = f"{mark} {self.action}: {self.message}"
        if self.error and self.error.details:
            line += f"\n  Reason: {self.error.details}"
        return line

    def __bool__(self) -> bool:
        return self.success
