"""Thin ADK tool adapter around the existing ``AndroidAutomation`` facade.

Every function here is a tool the LLM can call. They contain no planning logic
and no Android implementation: each one forwards to the deterministic
automation layer in ``tools/android-ui-automation`` and returns its structured
response as a plain, JSON-serialisable dict.

Adapter-level shaping (kept deliberately small):
  * UI elements are compacted (empty fields dropped) to save model tokens.
  * An ``agent_note`` is attached to certain error codes to help the model
    interpret them (for example, inconclusive text verification).
  * Calls are serialised with a lock so parallel tool calls from the model can
    never interleave taps on the device.

NOTE: no ``from __future__ import annotations`` here: ADK builds the tool
schema from the real type hints of these functions.
"""

import functools
import importlib
import importlib.util
import json
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, Optional

from .config import Settings, get_settings

_AUTOMATION_ALIAS = "android_ui_automation"
_LOCK = threading.RLock()
_AUTOMATION: Any = None

# --------------------------------------------------------------------------- #
# Loading the existing automation project
# --------------------------------------------------------------------------- #


def load_automation_package(project_path: Path) -> ModuleType:
    """Import ``<project_path>/src`` as the package ``android_ui_automation``.

    Both this agent and the automation project use a top-level package called
    ``src``; loading the automation project under an alias avoids the clash
    without copying or modifying any of its code.
    """
    if _AUTOMATION_ALIAS in sys.modules:
        return sys.modules[_AUTOMATION_ALIAS]
    package_dir = project_path / "src"
    init_file = package_dir / "__init__.py"
    if not init_file.is_file():
        raise FileNotFoundError(
            f"Android automation project not found at {project_path}. "
            "Set ANDROID_AUTOMATION_PATH to the tools/android-ui-automation directory."
        )
    spec = importlib.util.spec_from_file_location(
        _AUTOMATION_ALIAS, init_file, submodule_search_locations=[str(package_dir)]
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Could not load automation package from {package_dir}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_AUTOMATION_ALIAS] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(_AUTOMATION_ALIAS, None)
        raise
    return module


def get_automation() -> Any:
    """Return the shared real ``AndroidAutomation`` instance (created lazily)."""
    global _AUTOMATION
    if _AUTOMATION is None:
        settings: Settings = get_settings()
        package = load_automation_package(settings.automation_path)
        config = package.Config(
            adb_path=settings.adb_path,
            device_id=settings.device_id,
            command_timeout=settings.command_timeout,
            ui_wait_timeout=settings.ui_wait_timeout,
        )
        _AUTOMATION = package.AndroidAutomation(config)
    return _AUTOMATION


def reset_automation() -> None:
    """Forget the cached instance (used after changing settings, e.g. in tests)."""
    global _AUTOMATION
    _AUTOMATION = None


# --------------------------------------------------------------------------- #
# Result shaping
# --------------------------------------------------------------------------- #

_AGENT_NOTES: Dict[str, str] = {
    "TEXT_VERIFICATION_FAILED": (
        "The text was sent to the field, but UIAutomator could not read the same "
        "value back. This is INCONCLUSIVE, not proof of failure. Observe the next "
        "UI state (get_ui_hierarchy or verify_state) before deciding; do not "
        "blindly retry or blindly assume success."
    ),
    "EXPECTED_STATE_NOT_REACHED": (
        "The action itself executed; only the expected state was not observed. "
        "Inspect the UI to see where you actually are before retrying."
    ),
    "ELEMENT_NOT_FOUND": (
        "Inspect with get_ui_hierarchy and look for an alternative selector "
        "(text, content_description, resource_id, hint, class) before retrying."
    ),
    "ELEMENT_NOT_INTERACTABLE": (
        "The element exists but cannot be used now (disabled, hidden or off-screen). "
        "Consider scrolling with swipe, waiting, or navigating to the right screen."
    ),
    "UI_HIERARCHY_UNAVAILABLE": (
        "The UI could not be read (animation or secure screen). Call wait(1) and "
        "retry once."
    ),
    "DEVICE_UNRESPONSIVE": "The device stopped responding. Check is_device_connected.",
    "ADB_NOT_FOUND": "Environment problem: adb is not installed or ADB_PATH is wrong. Stop and report it.",
    "DEVICE_NOT_CONNECTED": "Environment problem: no usable device. Stop and report it; retrying will not help.",
    "MULTIPLE_DEVICES": "Environment problem: several devices are connected and ANDROID_DEVICE_ID is not set. Stop and report it.",
}


def _compact_element(el: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only the fields useful for choosing selectors; drop empty values."""
    out: Dict[str, Any] = {}
    for key in ("text", "resource_id", "content_description", "hint"):
        if el.get(key):
            out[key] = el[key]
    out["class"] = str(el.get("class_name", "")).rsplit(".", 1)[-1]
    for key in ("clickable", "focused", "scrollable", "password", "checked"):
        if el.get(key):
            out[key] = True
    if el.get("enabled") is False:
        out["enabled"] = False
    if el.get("center"):
        out["center"] = el["center"]
    return out


def _to_serialisable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _run(tool: str, **kwargs: Any) -> Dict[str, Any]:
    """Call an automation tool by name and return a JSON-safe dict. Never raises."""
    try:
        with _LOCK:
            response = get_automation().call(tool, **kwargs)
        result = _to_serialisable(response.to_dict())
    except Exception as exc:  # noqa: BLE001 - tools must never raise into the model loop
        return {
            "success": False,
            "action": tool,
            "message": "Tool adapter error",
            "data": {},
            "error": {"code": "ADAPTER_ERROR", "details": f"{type(exc).__name__}: {exc}"},
        }
    code = (result.get("error") or {}).get("code")
    if code in _AGENT_NOTES:
        result["agent_note"] = _AGENT_NOTES[code]
    return result


def _selector_kwargs(**kwargs: Any) -> Dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}


# --------------------------------------------------------------------------- #
# Device tools
# --------------------------------------------------------------------------- #


def list_devices() -> dict:
    """List Android devices and emulators visible to ADB.

    Use this to discover which devices exist, or to diagnose why nothing works.
    Returns data.devices, each with serial, state ("device" means ready,
    "unauthorized" or "offline" means unusable), is_emulator and model.
    If several devices are listed the user must choose one (ANDROID_DEVICE_ID).
    """
    return _run("list_devices")


def get_device_info() -> dict:
    """Get model, manufacturer, Android version, SDK level and whether it is an emulator.

    Use this when behaviour may depend on the Android version or device type.
    Not needed for ordinary tasks.
    """
    return _run("get_device_info")


def get_screen_size() -> dict:
    """Get the screen width and height in pixels (data.width, data.height).

    Only needed when you must compute raw swipe coordinates (for example to
    scroll). Prefer semantic selectors for everything else.
    """
    return _run("get_screen_size")


def is_device_connected() -> dict:
    """Check that the configured Android device is connected and ready.

    Use this first when the device state is unknown. success=true means the
    query ran; the answer is data.connected (true or false). If it is false
    or the call fails, stop and report the environment problem.
    """
    return _run("is_device_connected")


# --------------------------------------------------------------------------- #
# Application tools
# --------------------------------------------------------------------------- #


def find_installed_package(name_hint: str) -> dict:
    """Find installed Android package names that contain a text hint.

    Use this to turn an app name the user mentioned (for example "brave",
    "chrome", "calculator") into the package name that launch_app needs.
    Matching is a case-insensitive substring match on the package name, so the
    hint should be a short lowercase word. Returns data.packages (at most 25).
    Several matches are possible; choose the most plausible one, and mention
    your choice if it is ambiguous. An empty list means the app is probably not
    installed or the hint is wrong; try one alternative hint before giving up.

    Args:
        name_hint: Short word to look for inside package names, e.g. "brave".
    """
    hint = (name_hint or "").strip().lower()
    if not hint:
        return {
            "success": False, "action": "find_installed_package",
            "message": "name_hint must not be empty", "data": {},
            "error": {"code": "INVALID_ARGUMENT", "details": "Provide a short app-name hint."},
        }
    try:
        with _LOCK:
            automation = get_automation()
            result = automation.adb.shell("pm", "list", "packages")
        packages = sorted(
            {
                line.split(":", 1)[1].strip()
                for line in result.stdout.splitlines()
                if line.startswith("package:") and hint in line.lower()
            }
        )
        return {
            "success": True, "action": "find_installed_package",
            "message": f"Found {len(packages)} matching package(s)",
            "data": {"name_hint": hint, "packages": packages[:25], "match_count": len(packages)},
        }
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", None)
        return {
            "success": False, "action": "find_installed_package",
            "message": getattr(exc, "message", "Could not list packages"), "data": {},
            "error": {
                "code": getattr(code, "value", None) or "COMMAND_FAILED",
                "details": getattr(exc, "details", "") or f"{type(exc).__name__}: {exc}",
            },
            **({"agent_note": _AGENT_NOTES[getattr(code, "value", "")]}
               if getattr(code, "value", "") in _AGENT_NOTES else {}),
        }


def launch_app(package_name: str) -> dict:
    """Launch an Android app by its package name (for example "com.android.chrome").

    Use this when the target app is not already in the foreground. Check
    is_app_running / get_current_activity first so you do not relaunch an app
    needlessly. If you only know the app's name, resolve the package with
    find_installed_package. success=true means the app process started; it does
    not guarantee which screen is showing, so inspect the UI afterwards.
    Failure code APP_LAUNCH_FAILED usually means the package is wrong or not
    installed.

    Args:
        package_name: Android package name, e.g. "com.brave.browser".
    """
    return _run("launch_app", package_name=package_name)


def stop_app(package_name: str) -> dict:
    """Force-stop an app. Only use when the user asked to close or restart it.

    This kills the app and can lose unsaved state, so never use it as a
    shortcut for navigation.

    Args:
        package_name: Android package name to stop.
    """
    return _run("stop_app", package_name=package_name)


def is_app_running(package_name: str) -> dict:
    """Check whether an app's process is running.

    success=true means the query ran; the answer is data.running. Running does
    not mean foreground: use get_current_activity to see which app is visible.

    Args:
        package_name: Android package name to check.
    """
    return _run("is_app_running", package_name=package_name)


def get_current_activity() -> dict:
    """Get the app and activity currently in the foreground.

    Returns data.package and data.activity. Use it to learn which app is
    showing before deciding whether to launch something, and as supporting
    evidence when verifying navigation between app screens. It cannot tell you
    web page contents inside a browser; use get_ui_hierarchy for that.
    """
    return _run("get_current_activity")


# --------------------------------------------------------------------------- #
# UI inspection tools
# --------------------------------------------------------------------------- #


def get_ui_hierarchy(only_useful: bool = True, max_elements: int = 80) -> dict:
    """Read the elements currently on screen.

    Use this to discover what you can interact with and to check the result of
    an action. Each element (data.elements) lists, when present: text,
    resource_id, content_description, hint, class, clickable/focused/scrollable
    flags, enabled=false if disabled, and center coordinates. Only elements
    visible to the user are returned. Do not call it repeatedly when nothing
    has changed. Web page content inside browsers is often exposed as text and
    content descriptions, but not always.

    Args:
        only_useful: If true (default) skip purely structural containers.
        max_elements: Cap on returned elements (default 80); data.truncated is
            true if more existed. Raise it only if you cannot find your target.
    """
    result = _run("get_ui_hierarchy", only_useful=only_useful)
    data = result.get("data") or {}
    elements = [e for e in data.get("elements", []) if e.get("visible_to_user", True)]
    limit = max(1, int(max_elements))
    data["total_visible"] = len(elements)
    data["truncated"] = len(elements) > limit
    data["elements"] = [_compact_element(e) for e in elements[:limit]]
    data["returned_count"] = len(data["elements"])
    data.pop("element_count", None)
    result["data"] = data
    return result


def find_element(
    text: Optional[str] = None,
    resource_id: Optional[str] = None,
    content_description: Optional[str] = None,
    class_name: Optional[str] = None,
    hint: Optional[str] = None,
    text_contains: Optional[str] = None,
    index: int = 0,
    timeout: Optional[float] = None,
) -> dict:
    """Look for one UI element and report its attributes.

    Use this to confirm that a specific element exists before acting, or to
    learn the exact text or resource_id of an element you only partly know
    (use text_contains for that). Give at least one selector. text and
    content_description match exactly; resource_id may be the full id
    ("com.app:id/url_bar") or the short id ("url_bar"); class_name may be the
    simple name ("EditText"). Returns data.element and data.match_count. If
    several elements match, index picks one (visible ones come first).
    ELEMENT_NOT_FOUND means nothing matched after waiting for timeout seconds.

    Args:
        text: Exact visible text.
        resource_id: Full or short resource id.
        content_description: Exact accessibility label.
        class_name: Android class, full or simple name.
        hint: Hint text of an input field.
        text_contains: Substring of the visible text.
        index: Which match to return when several match (default 0).
        timeout: Seconds to wait for it to appear (default from configuration).
    """
    result = _run(
        "find_element",
        **_selector_kwargs(
            text=text, resource_id=resource_id, content_description=content_description,
            class_name=class_name, hint=hint, text_contains=text_contains,
            index=index, timeout=timeout,
        ),
    )
    data = result.get("data") or {}
    if isinstance(data.get("element"), dict):
        data["element"] = _compact_element(data["element"])
    return result


def element_exists(
    text: Optional[str] = None,
    resource_id: Optional[str] = None,
    content_description: Optional[str] = None,
    class_name: Optional[str] = None,
    hint: Optional[str] = None,
    text_contains: Optional[str] = None,
    timeout: Optional[float] = 0,
) -> dict:
    """Check quickly whether an element is currently on screen.

    Same selectors as find_element. success=true means the check ran; the
    answer is data.exists. By default it does not wait (timeout 0); pass a
    timeout in seconds to wait for the element to appear. Use it for cheap
    yes/no checks, and find_element when you need the element's details.

    Args:
        text: Exact visible text.
        resource_id: Full or short resource id.
        content_description: Exact accessibility label.
        class_name: Android class, full or simple name.
        hint: Hint text of an input field.
        text_contains: Substring of the visible text.
        timeout: Seconds to wait for the element (default 0 = no waiting).
    """
    return _run(
        "element_exists",
        **_selector_kwargs(
            text=text, resource_id=resource_id, content_description=content_description,
            class_name=class_name, hint=hint, text_contains=text_contains, timeout=timeout,
        ),
    )


# --------------------------------------------------------------------------- #
# Semantic action tools
# --------------------------------------------------------------------------- #


def click_element(
    text: Optional[str] = None,
    resource_id: Optional[str] = None,
    content_description: Optional[str] = None,
    class_name: Optional[str] = None,
    index: int = 0,
    expected_text: Optional[str] = None,
    expected_resource_id: Optional[str] = None,
    expected_activity: Optional[str] = None,
    timeout: Optional[float] = None,
) -> dict:
    """Click a visible UI element identified semantically.

    Use this whenever the target can be identified by resource_id, exact text,
    or content_description; it is far more reliable than raw coordinate taps.
    Give at least one selector (resource_id is the most stable). It finds the
    element, checks it is enabled and on screen, taps its centre, and confirms
    the device is still responsive. It does NOT accept hint or text_contains;
    use find_element first to learn the exact text if you only know part of it.

    To verify the outcome in the same call, pass expected_text (substring of any
    visible text or content description that should appear afterwards),
    expected_resource_id, or expected_activity. If the click ran but the
    expected state did not appear, you get EXPECTED_STATE_NOT_REACHED: the
    click executed, but the intended result was not seen.

    Args:
        text: Exact visible text of the element.
        resource_id: Full or short resource id.
        content_description: Exact accessibility label.
        class_name: Android class, full or simple name (combine with index).
        index: Which match to click when several match (default 0).
        expected_text: Text that should be on screen after the click.
        expected_resource_id: Resource id that should be on screen after the click.
        expected_activity: Substring of the activity that should be foreground afterwards.
        timeout: Seconds to wait for the element / expected state.
    """
    return _run(
        "click_element",
        **_selector_kwargs(
            text=text, resource_id=resource_id, content_description=content_description,
            class_name=class_name, index=index, expected_text=expected_text,
            expected_resource_id=expected_resource_id, expected_activity=expected_activity,
            timeout=timeout,
        ),
    )


def input_text(
    text: str,
    resource_id: Optional[str] = None,
    hint: Optional[str] = None,
    content_description: Optional[str] = None,
    class_name: Optional[str] = None,
    index: int = 0,
    clear_first: bool = True,
    verify: bool = True,
) -> dict:
    """Enter text into an input field identified semantically.

    Use this to type into a text box, search box or address bar. It finds the
    field (by resource_id, hint, content_description or class_name), taps it to
    focus, clears existing text by default, types, and tries to read the value
    back. With no selector at all it targets the currently focused field.
    Only printable ASCII is supported (no newlines: use press_enter to submit).

    Important: reading the value back through UIAutomator is sometimes
    impossible even when the text really was entered. TEXT_VERIFICATION_FAILED
    is therefore INCONCLUSIVE: observe the next UI state before concluding.
    Typing does not submit anything; use press_enter or click a submit control.

    Args:
        text: Text to type (printable ASCII).
        resource_id: Full or short resource id of the field.
        hint: Hint text shown in the empty field.
        content_description: Accessibility label of the field.
        class_name: Android class, e.g. "EditText".
        index: Which match to use when several fields match.
        clear_first: Clear existing content first (default true).
        verify: Read the field back to verify (default true).
    """
    return _run(
        "input_text",
        text=text,
        **_selector_kwargs(
            resource_id=resource_id, hint=hint, content_description=content_description,
            class_name=class_name, index=index, clear_first=clear_first, verify=verify,
        ),
    )


def verify_state(
    expected_text: Optional[str] = None,
    expected_resource_id: Optional[str] = None,
    expected_activity: Optional[str] = None,
    timeout: Optional[float] = None,
) -> dict:
    """Check that the UI currently shows an expected state, without acting.

    Use this after an important action to confirm the intended outcome (for
    example that a page title, a URL, or a screen heading is now visible).
    Provide at least one expectation; all provided ones must hold. expected_text
    is a substring match against any visible text or content description. It
    polls until the timeout, which also makes it a good way to wait for a
    screen to load. success=true means the state was observed;
    EXPECTED_STATE_NOT_REACHED means it was not seen in time (inspect the UI
    next).

    Args:
        expected_text: Substring that should be visible.
        expected_resource_id: Resource id that should be present.
        expected_activity: Substring of the foreground activity.
        timeout: Seconds to wait (default from configuration).
    """
    return _run(
        "verify_state",
        **_selector_kwargs(
            expected_text=expected_text, expected_resource_id=expected_resource_id,
            expected_activity=expected_activity, timeout=timeout,
        ),
    )


# --------------------------------------------------------------------------- #
# Raw input tools
# --------------------------------------------------------------------------- #


def type_text(text: str) -> dict:
    """Type text into whatever input field currently has keyboard focus.

    Use only when a field is already focused and has no usable selector;
    otherwise prefer input_text. No verification is possible. Printable ASCII
    only.

    Args:
        text: Text to type.
    """
    return _run("type_text", text=text)


def tap(x: int, y: int) -> dict:
    """Tap raw screen coordinates (pixels).

    Last resort, only when no semantic selector can identify the target. Take
    coordinates from the "center" of an element you actually observed, never
    guess them. Does not verify anything.

    Args:
        x: Horizontal pixel position.
        y: Vertical pixel position.
    """
    return _run("tap", x=x, y=y)


def swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> dict:
    """Swipe between two screen coordinates, for example to scroll a list.

    To scroll down, swipe from a lower point to a higher point (y1 > y2).
    Get the screen size with get_screen_size and keep the points inside the
    screen. Re-inspect the UI afterwards: a swipe cannot tell you whether
    anything moved.

    Args:
        x1: Start x position in pixels.
        y1: Start y position in pixels.
        x2: End x position in pixels.
        y2: End y position in pixels.
        duration_ms: Swipe duration in milliseconds (default 300).
    """
    return _run("swipe", x1=x1, y1=y1, x2=x2, y2=y2, duration_ms=duration_ms)


def wait(seconds: float) -> dict:
    """Pause for a number of seconds (0 to 300).

    Use briefly (1-3 s) to let the UI settle after an action or while a page
    loads, then inspect. Prefer verify_state with a timeout, which waits only as
    long as needed.

    Args:
        seconds: How long to wait.
    """
    return _run("wait", seconds=seconds)


# --------------------------------------------------------------------------- #
# Navigation tools
# --------------------------------------------------------------------------- #


def press_back() -> dict:
    """Press the Back key. Use to leave a screen, dismiss a dialog or keyboard, or recover from a wrong screen."""
    return _run("press_back")


def press_home() -> dict:
    """Press the Home key, sending the current app to the background and showing the launcher."""
    return _run("press_home")


def press_enter() -> dict:
    """Press the Enter key, typically to submit a search or address typed into a field.

    success=true only means the key was sent; verify the resulting screen
    afterwards.
    """
    return _run("press_enter")


def press_recent_apps() -> dict:
    """Open the recent-apps (app switcher) screen."""
    return _run("press_recent_apps")


# --------------------------------------------------------------------------- #
# Screenshot
# --------------------------------------------------------------------------- #


def take_screenshot(path: Optional[str] = None) -> dict:
    """Save a screenshot as a PNG file and return its path (data.path).

    The saved image is for humans and debugging: you cannot view images in
    this version, so do not use it to decide what to do. Use get_ui_hierarchy
    to observe the screen.

    Args:
        path: Optional output file path (default: a fixed temp file).
    """
    return _run("take_screenshot", **_selector_kwargs(path=path))


# --------------------------------------------------------------------------- #
# Tool registry
# --------------------------------------------------------------------------- #


def _serialised(fn: Callable[..., dict]) -> Callable[..., dict]:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict:
        with _LOCK:
            return fn(*args, **kwargs)

    return wrapper


ANDROID_TOOLS = [
    _serialised(fn)
    for fn in (
        is_device_connected, list_devices, get_device_info, get_screen_size,
        find_installed_package, launch_app, stop_app, is_app_running, get_current_activity,
        get_ui_hierarchy, find_element, element_exists,
        click_element, input_text, verify_state,
        type_text, tap, swipe, wait,
        press_back, press_home, press_enter, press_recent_apps,
        take_screenshot,
    )
]
