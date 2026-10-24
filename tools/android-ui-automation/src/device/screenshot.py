"""Screenshot capture via ``adb exec-out screencap -p``."""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path
from typing import Optional

from ..adb.client import ADBClient
from ..errors import ToolError, guarded
from ..models.responses import ActionResponse, ErrorCode

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def default_screenshot_path() -> Path:
    return Path(tempfile.gettempdir()) / "android_screenshot.png"


class ScreenshotService:
    def __init__(self, adb: ADBClient) -> None:
        self.adb = adb

    @guarded("screenshot")
    def take_screenshot(self, path: Optional[str] = None) -> ActionResponse:
        target = Path(path).expanduser() if path else default_screenshot_path()
        result = self.adb.exec_out("screencap", "-p", timeout=max(self.adb.timeout, 30))
        png = result.stdout_bytes
        if not png.startswith(_PNG_MAGIC):
            # Some old adb versions translate LF -> CRLF; undo it.
            fixed = png.replace(b"\r\n", b"\n")
            if fixed.startswith(_PNG_MAGIC):
                png = fixed
            else:
                raise ToolError(
                    ErrorCode.SCREENSHOT_FAILED,
                    "Device did not return a valid PNG",
                    result.stderr.strip()[:300] or "screencap output was not a PNG",
                )
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(png)
        except OSError as exc:
            raise ToolError(ErrorCode.SCREENSHOT_FAILED, "Could not save screenshot", str(exc)) from exc

        data = {"path": str(target), "size_bytes": len(png)}
        if len(png) >= 24:
            width, height = struct.unpack(">II", png[16:24])
            data.update({"width": width, "height": height})
        return ActionResponse.ok("screenshot", "Screenshot saved", data)
