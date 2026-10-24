"""Builders for the device-side commands used by the tool."""

from __future__ import annotations

import re
import shlex
from typing import List

from ..errors import ToolError
from ..models.responses import ErrorCode

KEYCODE_HOME = 3
KEYCODE_BACK = 4
KEYCODE_ENTER = 66
KEYCODE_DEL = 67
KEYCODE_MOVE_END = 123
KEYCODE_APP_SWITCH = 187

_PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)*$")


def validate_package(package: str) -> str:
    if not isinstance(package, str) or not _PACKAGE_RE.match(package):
        raise ToolError(
            ErrorCode.INVALID_ARGUMENT,
            "Invalid package name",
            f"{package!r} is not a valid Android package name",
        )
    return package


def validate_text(text: str, allow_empty: bool = False) -> str:
    """`adb shell input text` only reliably supports printable ASCII."""
    if not isinstance(text, str):
        raise ToolError(ErrorCode.INVALID_ARGUMENT, "Text must be a string")
    if not text and not allow_empty:
        raise ToolError(ErrorCode.INVALID_ARGUMENT, "Text must not be empty")
    if not text.isascii() or any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise ToolError(
            ErrorCode.INVALID_ARGUMENT,
            "Unsupported characters in text",
            "Only printable ASCII is supported by 'input text' "
            "(use press_enter() for newlines).",
        )
    return text


def launch_app(package: str) -> List[str]:
    return ["monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"]


def force_stop(package: str) -> List[str]:
    return ["am", "force-stop", package]


def tap(x: int, y: int) -> List[str]:
    return ["input", "tap", str(int(x)), str(int(y))]


def swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int) -> List[str]:
    return ["input", "swipe", str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(duration_ms))]


def keyevent(*codes: int) -> List[str]:
    return ["input", "keyevent", *[str(c) for c in codes]]


def input_text(text: str) -> List[str]:
    """Spaces become ``%s``; the whole string is single-quoted for the device shell."""
    return ["input", "text", shlex.quote(text.replace(" ", "%s"))]
