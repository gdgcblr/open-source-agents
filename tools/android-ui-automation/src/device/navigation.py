"""Hardware-key navigation actions."""

from __future__ import annotations

from ..adb import commands
from ..adb.client import ADBClient
from ..errors import guarded
from ..models.responses import ActionResponse


class Navigation:
    def __init__(self, adb: ADBClient) -> None:
        self.adb = adb

    def _press(self, action: str, label: str, keycode: int) -> ActionResponse:
        self.adb.shell(*commands.keyevent(keycode))
        return ActionResponse.ok(action, f"{label} key pressed", {"keycode": keycode})

    @guarded("press_back")
    def press_back(self) -> ActionResponse:
        return self._press("press_back", "Back", commands.KEYCODE_BACK)

    @guarded("press_home")
    def press_home(self) -> ActionResponse:
        return self._press("press_home", "Home", commands.KEYCODE_HOME)

    @guarded("press_enter")
    def press_enter(self) -> ActionResponse:
        return self._press("press_enter", "Enter", commands.KEYCODE_ENTER)

    @guarded("press_recent_apps")
    def press_recent_apps(self) -> ActionResponse:
        return self._press("press_recent_apps", "Recent apps", commands.KEYCODE_APP_SWITCH)
