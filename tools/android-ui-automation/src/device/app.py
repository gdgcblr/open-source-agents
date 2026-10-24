"""Application lifecycle: launch, stop, running-state, current activity."""

from __future__ import annotations

import re
import time
from typing import Optional, Tuple

from ..adb import commands
from ..adb.client import ADBClient
from ..errors import ToolError, guarded
from ..models.responses import ActionResponse, ErrorCode

_ACTIVITY_RE = re.compile(r"([A-Za-z][\w.]*)/([\w.$]+)")


class AppManager:
    def __init__(self, adb: ADBClient, wait_timeout: float = 5.0) -> None:
        self.adb = adb
        self.wait_timeout = wait_timeout

    # -- internal helpers ---------------------------------------------------
    def process_running(self, package: str) -> bool:
        r = self.adb.shell("pidof", package, check=False)
        combined = r.stdout + r.stderr
        if "not found" not in combined:
            return r.ok and bool(r.stdout.strip())
        # Very old devices without pidof: fall back to ps.
        for ps_args in (("ps", "-A"), ("ps",)):
            out = self.adb.shell(*ps_args, check=False).stdout
            if out.strip():
                for line in out.splitlines():
                    parts = line.split()
                    if parts and (parts[-1] == package or parts[-1].startswith(package + ":")):
                        return True
                return False
        return False

    def current_component(self) -> Optional[Tuple[str, str]]:
        """Return (package, activity-class) of the resumed activity, if known."""
        out = self.adb.shell("dumpsys", "activity", "activities", check=False).stdout
        for line in out.splitlines():
            if any(k in line for k in ("topResumedActivity", "mResumedActivity", "ResumedActivity:")):
                m = _ACTIVITY_RE.search(line)
                if m:
                    return self._normalise(m.group(1), m.group(2))
        out = self.adb.shell("dumpsys", "window", check=False).stdout
        for line in out.splitlines():
            if "mCurrentFocus" in line or "mFocusedApp" in line:
                m = _ACTIVITY_RE.search(line)
                if m:
                    return self._normalise(m.group(1), m.group(2))
        return None

    @staticmethod
    def _normalise(package: str, activity: str) -> Tuple[str, str]:
        if activity.startswith("."):
            activity = package + activity
        return package, activity

    def current_activity_name(self) -> Optional[str]:
        comp = self.current_component()
        return f"{comp[0]}/{comp[1]}" if comp else None

    # -- tools ---------------------------------------------------------------
    @guarded("launch_app")
    def launch_app(self, package_name: str) -> ActionResponse:
        package = commands.validate_package(package_name)
        data = {"package": package}
        r = self.adb.shell(*commands.launch_app(package), check=False)
        out = (r.stdout + r.stderr).strip()
        if "No activities found" in out or "monkey aborted" in out or (
            not r.ok and "Events injected" not in out
        ):
            return ActionResponse.fail(
                "launch_app",
                ErrorCode.APP_LAUNCH_FAILED,
                "Application could not be launched",
                out[:300] or "Launch command failed",
                data,
            )
        deadline = time.monotonic() + self.wait_timeout
        while True:
            if self.process_running(package):
                return ActionResponse.ok(
                    "launch_app", "Application launched successfully", data
                )
            if time.monotonic() >= deadline:
                break
            time.sleep(0.3)
        return ActionResponse.fail(
            "launch_app",
            ErrorCode.APP_LAUNCH_FAILED,
            "Application could not be launched",
            f"Launch command ran but no process for {package} appeared "
            f"within {self.wait_timeout}s",
            data,
        )

    @guarded("stop_app")
    def stop_app(self, package_name: str) -> ActionResponse:
        package = commands.validate_package(package_name)
        data = {"package": package}
        self.adb.shell(*commands.force_stop(package))
        time.sleep(0.3)
        if self.process_running(package):
            return ActionResponse.fail(
                "stop_app",
                ErrorCode.APP_STOP_FAILED,
                "Application is still running after force-stop",
                f"Process for {package} is still alive",
                data,
            )
        return ActionResponse.ok("stop_app", "Application stopped", data)

    @guarded("is_app_running")
    def is_app_running(self, package_name: str) -> ActionResponse:
        """``success`` means the query ran; the answer is in ``data['running']``."""
        package = commands.validate_package(package_name)
        running = self.process_running(package)
        return ActionResponse.ok(
            "is_app_running",
            "Application is running" if running else "Application is not running",
            {"package": package, "running": running},
        )

    @guarded("get_current_activity")
    def get_current_activity(self) -> ActionResponse:
        comp = self.current_component()
        if comp is None:
            raise ToolError(
                ErrorCode.COMMAND_FAILED,
                "Could not determine current activity",
                "dumpsys output did not contain a resumed activity",
            )
        package, activity = comp
        return ActionResponse.ok(
            "get_current_activity",
            f"Current activity is {package}/{activity}",
            {"package": package, "activity": activity, "component": f"{package}/{activity}"},
        )
