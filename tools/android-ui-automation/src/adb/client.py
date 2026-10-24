"""Thin, deterministic wrapper around the ``adb`` executable."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Sequence

from ..errors import ADBError
from ..models.responses import ErrorCode


@dataclass
class CommandResult:
    args: List[str]
    returncode: int
    stdout_bytes: bytes
    stderr_bytes: bytes

    @property
    def stdout(self) -> str:
        return self.stdout_bytes.decode("utf-8", errors="replace")

    @property
    def stderr(self) -> str:
        return self.stderr_bytes.decode("utf-8", errors="replace")

    @property
    def ok(self) -> bool:
        return self.returncode == 0


_DEVICE_GONE_MARKERS = (
    "no devices/emulators found",
    "device offline",
    "device unauthorized",
    "device still authorizing",
    "error: closed",
    "no devices found",
)


def classify_error(stderr: str) -> Optional[ErrorCode]:
    """Map adb stderr output to a well-known error code, if any."""
    s = stderr.lower()
    if "more than one device" in s or "more than one emulator" in s:
        return ErrorCode.MULTIPLE_DEVICES
    if any(m in s for m in _DEVICE_GONE_MARKERS) or re.search(r"device '.*' not found", s):
        return ErrorCode.DEVICE_NOT_CONNECTED
    return None


class ADBClient:
    """Runs adb commands, optionally targeting a specific device serial."""

    def __init__(
        self,
        adb_path: str = "adb",
        device_id: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.adb_path = adb_path
        self.device_id = device_id
        self.timeout = timeout

    def run(
        self,
        args: Sequence[str],
        *,
        timeout: Optional[float] = None,
        use_device: bool = True,
        check: bool = True,
    ) -> CommandResult:
        cmd: List[str] = [self.adb_path]
        if use_device and self.device_id:
            cmd += ["-s", self.device_id]
        cmd += list(args)
        try:
            proc = subprocess.run(
                cmd, capture_output=True, timeout=timeout or self.timeout, check=False
            )
        except FileNotFoundError as exc:
            raise ADBError(
                ErrorCode.ADB_NOT_FOUND,
                "ADB executable not found",
                f"Could not execute {self.adb_path!r}. Install Android platform-tools "
                "or set ADB_PATH.",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ADBError(
                ErrorCode.COMMAND_TIMEOUT,
                "ADB command timed out",
                f"{' '.join(cmd)} exceeded {timeout or self.timeout}s",
            ) from exc

        result = CommandResult(cmd, proc.returncode, proc.stdout, proc.stderr)
        if check and not result.ok:
            text = result.stderr.strip() or result.stdout.strip()
            code = classify_error(result.stderr) or ErrorCode.COMMAND_FAILED
            raise ADBError(code, "ADB command failed", text[:500])
        return result

    def shell(
        self, *args: str, timeout: Optional[float] = None, check: bool = True
    ) -> CommandResult:
        return self.run(["shell", *args], timeout=timeout, check=check)

    def exec_out(
        self, *args: str, timeout: Optional[float] = None, check: bool = True
    ) -> CommandResult:
        """Like ``shell`` but binary-safe (no CRLF translation)."""
        return self.run(["exec-out", *args], timeout=timeout, check=check)
