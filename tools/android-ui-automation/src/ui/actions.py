"""Semantic UI actions with verification: click and text input."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..adb import commands
from ..device.app import AppManager
from ..device.device import DeviceManager
from ..device.input import InputController
from ..errors import ToolError, guarded
from ..models.responses import ActionResponse, ErrorCode
from .element import Element, Selector
from .hierarchy import UIHierarchy, UIInspector

_POLL_INTERVAL = 0.5
_FOCUS_SETTLE = 0.3
_DEL_CHUNK = 100


@dataclass(frozen=True)
class Expectation:
    """Post-action UI state. All provided conditions must hold.

    ``text`` is a substring match against any element's text or content
    description.
    """

    text: Optional[str] = None
    resource_id: Optional[str] = None
    activity: Optional[str] = None

    def is_empty(self) -> bool:
        return self.text is None and self.resource_id is None and self.activity is None

    def describe(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if self.text is not None:
            out["expected_text"] = self.text
        if self.resource_id is not None:
            out["expected_resource_id"] = self.resource_id
        if self.activity is not None:
            out["expected_activity"] = self.activity
        return out


class UIActions:
    def __init__(
        self,
        inspector: UIInspector,
        input_ctl: InputController,
        apps: AppManager,
        device: DeviceManager,
        settle_seconds: float = 0.5,
    ) -> None:
        self.inspector = inspector
        self.input = input_ctl
        self.apps = apps
        self.device = device
        self.settle_seconds = settle_seconds

    # -- helpers ---------------------------------------------------------------
    def _interactable_problem(self, el: Element) -> Optional[str]:
        if not el.enabled:
            return "Element is disabled"
        if not el.visible_to_user:
            return "Element is not visible to the user"
        if el.bounds.width <= 0 or el.bounds.height <= 0:
            return "Element has empty bounds"
        try:
            width, height = self.device.screen_size()
        except ToolError:
            return None  # cannot check; do not block
        cx, cy = el.bounds.center
        if not (0 <= cx < width and 0 <= cy < height):
            return "Element is outside the visible screen (scrolling may be required)"
        return None

    def _expectation_met(self, exp: Expectation, h: UIHierarchy) -> bool:
        if exp.text is not None and not h.contains_text(exp.text):
            return False
        if exp.resource_id is not None and not h.find(Selector(resource_id=exp.resource_id)):
            return False
        if exp.activity is not None:
            current = self.apps.current_activity_name() or ""
            if exp.activity not in current:
                return False
        return True

    def _wait_for_expectation(
        self, exp: Expectation, timeout: float
    ) -> Tuple[bool, Optional[UIHierarchy]]:
        deadline = time.monotonic() + timeout
        last: Optional[UIHierarchy] = None
        while True:
            try:
                last = self.inspector.reader.dump()
                if self._expectation_met(exp, last):
                    return True, last
            except ToolError:
                pass  # UI may be mid-transition; keep polling until the deadline
            if time.monotonic() >= deadline:
                return False, last
            time.sleep(_POLL_INTERVAL)

    # -- tools -------------------------------------------------------------------
    @guarded("click")
    def click_element(
        self,
        text: Optional[str] = None,
        resource_id: Optional[str] = None,
        content_description: Optional[str] = None,
        class_name: Optional[str] = None,
        index: int = 0,
        expected_text: Optional[str] = None,
        expected_resource_id: Optional[str] = None,
        expected_activity: Optional[str] = None,
        timeout: Optional[float] = None,
        wait_after: Optional[float] = None,
    ) -> ActionResponse:
        selector = Selector(
            text=text, resource_id=resource_id,
            content_description=content_description, class_name=class_name,
        )
        self.inspector.require_selector(selector)
        target: Dict[str, Any] = dict(selector.describe())
        if index:
            target["index"] = index
        expectation = Expectation(expected_text, expected_resource_id, expected_activity)
        wait_timeout = self.inspector.default_timeout if timeout is None else timeout

        # 1-2. Inspect the UI and locate the element.
        hierarchy, matches = self.inspector.locate(selector, wait_timeout)
        if not matches or index < 0 or index >= len(matches):
            details = f"No element matching {selector.describe_str()} was found"
            if matches:
                details = (f"Only {len(matches)} element(s) matched "
                           f"{selector.describe_str()}; index {index} is out of range")
            return ActionResponse.fail(
                "click", ErrorCode.ELEMENT_NOT_FOUND, "Element not found", details,
                {"target": target, "match_count": len(matches)},
            )
        el = matches[index]

        # 3. Verify it is interactable.
        problem = self._interactable_problem(el)
        if problem:
            return ActionResponse.fail(
                "click", ErrorCode.ELEMENT_NOT_INTERACTABLE, "Element is not interactable",
                problem, {"target": target, "element": el.to_dict()},
            )

        # 4. Click the element's centre.
        before = hierarchy.signature()
        x, y = el.bounds.center
        self.input.raw_tap(x, y)

        # 5. Let the UI settle, then make sure the device is still alive.
        time.sleep(self.settle_seconds if wait_after is None else wait_after)
        if not self.device.is_responsive():
            return ActionResponse.fail(
                "click", ErrorCode.DEVICE_UNRESPONSIVE,
                "Click executed but the device stopped responding",
                "adb shell probe failed after the tap",
                {"target": target, "tapped_at": [x, y]},
            )

        data: Dict[str, Any] = {
            "target": target,
            "element": el.to_dict(),
            "tapped_at": [x, y],
            "device_responsive": True,
        }

        # 6. Optional post-action verification.
        after: Optional[UIHierarchy] = None
        if not expectation.is_empty():
            met, after = self._wait_for_expectation(expectation, wait_timeout)
            data["expected"] = expectation.describe()
            data["ui_changed"] = (after.signature() != before) if after else None
            if not met:
                data["click_executed"] = True
                data["current_activity"] = self.apps.current_activity_name()
                return ActionResponse.fail(
                    "click", ErrorCode.EXPECTED_STATE_NOT_REACHED,
                    "Click executed but expected UI state was not reached",
                    f"Expected {expectation.describe()} was not found within {wait_timeout}s",
                    data,
                )
            data["expectation_met"] = True
        else:
            try:
                after = self.inspector.reader.dump()
                data["ui_changed"] = after.signature() != before
            except ToolError:
                data["ui_changed"] = None
        return ActionResponse.ok("click", "Element found and clicked", data)

    @guarded("input_text")
    def input_text(
        self,
        text: str,
        resource_id: Optional[str] = None,
        hint: Optional[str] = None,
        content_description: Optional[str] = None,
        class_name: Optional[str] = None,
        index: int = 0,
        clear_first: bool = True,
        verify: bool = True,
        timeout: Optional[float] = None,
    ) -> ActionResponse:
        commands.validate_text(text, allow_empty=clear_first)
        selector = Selector(
            resource_id=resource_id, hint=hint,
            content_description=content_description, class_name=class_name,
        )
        use_focused = selector.is_empty()
        target: Dict[str, Any] = {"focused_field": True} if use_focused else dict(selector.describe())
        wait_timeout = self.inspector.default_timeout if timeout is None else timeout

        if use_focused:
            hierarchy = self.inspector.reader.dump()
            matches: List[Element] = hierarchy.focused()
        else:
            hierarchy, matches = self.inspector.locate(selector, wait_timeout)
        if not matches or index < 0 or index >= len(matches):
            details = ("No focused input field was found" if use_focused
                       else f"No element matching {selector.describe_str()} was found")
            return ActionResponse.fail(
                "input_text", ErrorCode.ELEMENT_NOT_FOUND, "Input field not found",
                details, {"target": target, "match_count": len(matches)},
            )
        el = matches[index]
        problem = self._interactable_problem(el)
        if problem:
            return ActionResponse.fail(
                "input_text", ErrorCode.ELEMENT_NOT_INTERACTABLE,
                "Input field is not interactable", problem,
                {"target": target, "element": el.to_dict()},
            )

        # Focus the field, optionally clear it, then type.
        if not (use_focused and el.focused):
            x, y = el.bounds.center
            self.input.raw_tap(x, y)
            time.sleep(_FOCUS_SETTLE)
        if clear_first:
            self.input.raw_keys([commands.KEYCODE_MOVE_END])
            remaining = len(el.text) + 5
            while remaining > 0:
                n = min(remaining, _DEL_CHUNK)
                self.input.raw_keys([commands.KEYCODE_DEL] * n)
                remaining -= n
        if text:
            self.input.raw_type(text)

        data: Dict[str, Any] = {
            "target": target, "length": len(text), "cleared": clear_first, "verified": None,
        }
        if not self.device.is_responsive():
            return ActionResponse.fail(
                "input_text", ErrorCode.DEVICE_UNRESPONSIVE,
                "Text sent but the device stopped responding", "adb shell probe failed", data,
            )

        # Verify what the field now contains (not possible for password fields).
        if verify and text and not el.password:
            time.sleep(_FOCUS_SETTLE)
            after = self.inspector.reader.dump()
            found = after.focused() if use_focused else after.find(selector)
            actual = found[index].text if index < len(found) else None
            data["verified"] = actual == text
            if actual != text:
                return ActionResponse.fail(
                    "input_text", ErrorCode.TEXT_VERIFICATION_FAILED,
                    "Text was sent but the field does not contain the expected value",
                    f"Expected {text!r}, field contains {actual!r}", data,
                )
        return ActionResponse.ok("input_text", "Text entered into field", data)

    @guarded("verify_state")
    def verify_state(
        self,
        expected_text: Optional[str] = None,
        expected_resource_id: Optional[str] = None,
        expected_activity: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> ActionResponse:
        """Assert the current UI state without performing any action."""
        exp = Expectation(expected_text, expected_resource_id, expected_activity)
        if exp.is_empty():
            raise ToolError(ErrorCode.INVALID_ARGUMENT, "No expectation given")
        wait_timeout = self.inspector.default_timeout if timeout is None else timeout
        met, _ = self._wait_for_expectation(exp, wait_timeout)
        data = {"expected": exp.describe()}
        if met:
            return ActionResponse.ok("verify_state", "Expected UI state is present", data)
        data["current_activity"] = self.apps.current_activity_name()
        return ActionResponse.fail(
            "verify_state", ErrorCode.EXPECTED_STATE_NOT_REACHED,
            "Expected UI state was not reached",
            f"Expected {exp.describe()} was not found within {wait_timeout}s", data,
        )
