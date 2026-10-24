"""Coordinate-based and raw input: tap, swipe, type, wait."""

from __future__ import annotations

import time
from typing import Sequence

from ..adb import commands
from ..adb.client import ADBClient
from ..errors import ToolError, guarded
from ..models.responses import ActionResponse, ErrorCode

MAX_WAIT_SECONDS = 300.0


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ToolError(
            ErrorCode.INVALID_ARGUMENT, f"{name} must be a non-negative number", f"got {value!r}"
        )
    return int(value)


class InputController:
    def __init__(self, adb: ADBClient) -> None:
        self.adb = adb

    # -- raw helpers (raise on failure; used by higher layers) ---------------
    def raw_tap(self, x: int, y: int) -> None:
        self.adb.shell(*commands.tap(x, y))

    def raw_type(self, text: str) -> None:
        self.adb.shell(*commands.input_text(text))

    def raw_keys(self, codes: Sequence[int]) -> None:
        if codes:
            self.adb.shell(*commands.keyevent(*codes))

    # -- tools ---------------------------------------------------------------
    @guarded("tap")
    def tap(self, x: int, y: int) -> ActionResponse:
        xi, yi = _non_negative_int("x", x), _non_negative_int("y", y)
        self.raw_tap(xi, yi)
        return ActionResponse.ok("tap", f"Tapped at ({xi}, {yi})", {"x": xi, "y": yi})

    @guarded("swipe")
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> ActionResponse:
        coords = [_non_negative_int(n, v) for n, v in (("x1", x1), ("y1", y1), ("x2", x2), ("y2", y2))]
        dur = _non_negative_int("duration_ms", duration_ms)
        if dur == 0:
            raise ToolError(ErrorCode.INVALID_ARGUMENT, "duration_ms must be greater than 0")
        self.adb.shell(*commands.swipe(*coords, dur))
        return ActionResponse.ok(
            "swipe",
            f"Swiped from ({coords[0]}, {coords[1]}) to ({coords[2]}, {coords[3]})",
            {"from": [coords[0], coords[1]], "to": [coords[2], coords[3]], "duration_ms": dur},
        )

    @guarded("type_text")
    def type_text(self, text: str) -> ActionResponse:
        """Type into whatever field currently has focus (no verification possible)."""
        commands.validate_text(text)
        self.raw_type(text)
        return ActionResponse.ok(
            "type_text", "Text sent to focused field", {"length": len(text)}
        )

    @guarded("wait")
    def wait(self, seconds: float) -> ActionResponse:
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not (
            0 <= seconds <= MAX_WAIT_SECONDS
        ):
            raise ToolError(
                ErrorCode.INVALID_ARGUMENT,
                f"seconds must be between 0 and {int(MAX_WAIT_SECONDS)}",
                f"got {seconds!r}",
            )
        time.sleep(seconds)
        return ActionResponse.ok("wait", f"Waited {seconds}s", {"seconds": seconds})
