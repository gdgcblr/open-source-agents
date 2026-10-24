"""Facade exposing every tool as a method of one object.

This is the surface a future AI agent layer should call. Every method returns
an :class:`ActionResponse`; none raise.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from .adb.client import ADBClient
from .config import Config
from .device.app import AppManager
from .device.device import DeviceManager
from .device.input import InputController
from .device.navigation import Navigation
from .device.screenshot import ScreenshotService
from .models.responses import ActionResponse
from .ui.actions import UIActions
from .ui.hierarchy import HierarchyReader, UIInspector

TOOL_NAMES = (
    "list_devices", "get_device_info", "get_screen_size", "is_device_connected",
    "launch_app", "stop_app", "is_app_running", "get_current_activity",
    "get_ui_hierarchy", "find_element", "element_exists",
    "click_element", "type_text", "input_text", "verify_state",
    "press_back", "press_home", "press_enter", "press_recent_apps",
    "tap", "swipe", "wait", "take_screenshot",
)


class AndroidAutomation:
    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config.from_env()
        self.adb = ADBClient(
            self.config.adb_path, self.config.device_id, self.config.command_timeout
        )
        self._device = DeviceManager(self.adb)
        self._apps = AppManager(self.adb, self.config.ui_wait_timeout)
        self._nav = Navigation(self.adb)
        self._input = InputController(self.adb)
        self._shots = ScreenshotService(self.adb)
        self._inspector = UIInspector(HierarchyReader(self.adb), self.config.ui_wait_timeout)
        self._actions = UIActions(self._inspector, self._input, self._apps, self._device)

        # Device management
        self.list_devices = self._device.list_devices
        self.get_device_info = self._device.get_device_info
        self.get_screen_size = self._device.get_screen_size
        self.is_device_connected = self._device.is_device_connected
        # Application management
        self.launch_app = self._apps.launch_app
        self.stop_app = self._apps.stop_app
        self.is_app_running = self._apps.is_app_running
        self.get_current_activity = self._apps.get_current_activity
        # UI inspection
        self.get_ui_hierarchy = self._inspector.get_ui_hierarchy
        self.find_element = self._inspector.find_element
        self.element_exists = self._inspector.element_exists
        # Semantic actions
        self.click_element = self._actions.click_element
        self.input_text = self._actions.input_text
        self.verify_state = self._actions.verify_state
        # Raw input
        self.type_text = self._input.type_text
        self.tap = self._input.tap
        self.swipe = self._input.swipe
        self.wait = self._input.wait
        # Navigation
        self.press_back = self._nav.press_back
        self.press_home = self._nav.press_home
        self.press_enter = self._nav.press_enter
        self.press_recent_apps = self._nav.press_recent_apps
        # Screenshot
        self.take_screenshot = self._shots.take_screenshot

    def call(self, tool: str, **kwargs: Any) -> ActionResponse:
        """Dispatch a tool by name (whitelisted). Never raises."""
        if tool not in TOOL_NAMES:
            return ActionResponse.fail(
                tool, "UNKNOWN_TOOL", "Unknown tool", f"Available tools: {', '.join(TOOL_NAMES)}"
            )
        fn: Callable[..., ActionResponse] = getattr(self, tool)
        try:
            return fn(**kwargs)
        except TypeError as exc:  # wrong/missing arguments
            return ActionResponse.fail(tool, "INVALID_ARGUMENT", "Invalid arguments", str(exc))
