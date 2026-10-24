"""UI hierarchy retrieval, parsing and element lookup."""

from __future__ import annotations

import hashlib
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from ..adb.client import ADBClient
from ..errors import ToolError, guarded
from ..models.responses import ActionResponse, ErrorCode
from .element import Element, Selector

_REMOTE_DUMP_PATH = "/sdcard/window_dump.xml"
_POLL_INTERVAL = 0.5


@dataclass
class UIHierarchy:
    xml: str
    elements: List[Element] = field(default_factory=list)

    def find(self, selector: Selector) -> List[Element]:
        """Matches in document order, with on-screen-visible ones first."""
        matches = [e for e in self.elements if selector.matches(e)]
        matches.sort(key=lambda e: (not e.visible_to_user, e.order))
        return matches

    def focused(self) -> List[Element]:
        found = [e for e in self.elements if e.focused]
        found.sort(key=lambda e: (not e.is_editable, e.order))
        return found

    def contains_text(self, needle: str) -> bool:
        return any(needle in e.text or needle in e.content_description for e in self.elements)

    def signature(self) -> str:
        """Stable hash of what is on screen; used to detect UI changes."""
        parts = [
            (e.class_name, e.text, e.resource_id, e.content_description, e.bounds.left,
             e.bounds.top, e.bounds.right, e.bounds.bottom, e.checked, e.selected)
            for e in self.elements
        ]
        return hashlib.sha1(repr(parts).encode("utf-8")).hexdigest()


def parse_hierarchy(xml_text: str) -> UIHierarchy:
    start = xml_text.find("<hierarchy")
    end = xml_text.rfind("</hierarchy>")
    if start == -1 or end == -1:
        raise ToolError(
            ErrorCode.UI_HIERARCHY_UNAVAILABLE,
            "UI hierarchy could not be read",
            (xml_text.strip()[:300] or "uiautomator returned no hierarchy"),
        )
    body = xml_text[start : end + len("</hierarchy>")]
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ToolError(
            ErrorCode.UI_HIERARCHY_UNAVAILABLE, "UI hierarchy XML was malformed", str(exc)
        ) from exc

    elements: List[Element] = []

    def walk(node: ET.Element, parent: Optional[Element], depth: int) -> None:
        for child in node:
            if child.tag != "node":
                continue
            el = Element.from_xml(child, parent, depth, len(elements))
            elements.append(el)
            walk(child, el, depth + 1)

    walk(root, None, 0)
    return UIHierarchy(xml=body, elements=elements)


class HierarchyReader:
    """Dumps the current UI hierarchy via uiautomator."""

    def __init__(self, adb: ADBClient, attempts: int = 3) -> None:
        self.adb = adb
        self.attempts = attempts

    def dump(self) -> UIHierarchy:
        last_error: Optional[ToolError] = None
        for attempt in range(self.attempts):
            try:
                return parse_hierarchy(self._fetch_xml())
            except ToolError as exc:
                if exc.code == ErrorCode.UI_HIERARCHY_UNAVAILABLE:
                    last_error = exc
                    if attempt < self.attempts - 1:
                        time.sleep(0.5)
                    continue
                raise
        assert last_error is not None
        raise last_error

    def _fetch_xml(self) -> str:
        out = self.adb.exec_out("uiautomator", "dump", "/dev/tty", check=False).stdout
        if "<hierarchy" in out:
            return out
        # Fallback: dump to a file on the device and read it back.
        self.adb.shell("uiautomator", "dump", _REMOTE_DUMP_PATH, check=False)
        return self.adb.exec_out("cat", _REMOTE_DUMP_PATH, check=False).stdout


class UIInspector:
    """Locating elements and the public inspection tools."""

    def __init__(self, reader: HierarchyReader, default_timeout: float = 5.0) -> None:
        self.reader = reader
        self.default_timeout = default_timeout

    def locate(
        self, selector: Selector, timeout: Optional[float] = None
    ) -> Tuple[UIHierarchy, List[Element]]:
        """Poll the UI until the selector matches or ``timeout`` elapses."""
        wait = self.default_timeout if timeout is None else timeout
        deadline = time.monotonic() + wait
        while True:
            hierarchy = self.reader.dump()
            matches = hierarchy.find(selector)
            if matches or time.monotonic() >= deadline:
                return hierarchy, matches
            time.sleep(_POLL_INTERVAL)

    @staticmethod
    def require_selector(selector: Selector) -> None:
        if selector.is_empty():
            raise ToolError(
                ErrorCode.INVALID_ARGUMENT,
                "No element criteria given",
                "Provide at least one of text, resource_id, content_description, "
                "class_name, hint or text_contains.",
            )

    # -- tools ---------------------------------------------------------------
    @guarded("get_ui_hierarchy")
    def get_ui_hierarchy(
        self,
        include_xml: bool = False,
        only_useful: bool = True,
        save_path: Optional[str] = None,
    ) -> ActionResponse:
        """Return the current screen as structured elements.

        ``only_useful`` drops purely structural nodes (no text, id, description
        and neither clickable nor editable) to keep the output compact.
        """
        h = self.reader.dump()
        elements = h.elements
        if only_useful:
            elements = [
                e for e in elements
                if e.text or e.resource_id or e.content_description or e.clickable
                or e.is_editable or e.scrollable or e.checkable
            ]
        data = {
            "element_count": len(h.elements),
            "returned_count": len(elements),
            "elements": [e.to_dict() for e in elements],
        }
        if include_xml:
            data["xml"] = h.xml
        if save_path:
            try:
                p = Path(save_path).expanduser()
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(h.xml, encoding="utf-8")
                data["xml_path"] = str(p)
            except OSError as exc:
                raise ToolError(ErrorCode.COMMAND_FAILED, "Could not save XML", str(exc)) from exc
        return ActionResponse.ok(
            "get_ui_hierarchy", f"UI hierarchy retrieved ({len(h.elements)} elements)", data
        )

    @guarded("find_element")
    def find_element(
        self,
        text: Optional[str] = None,
        resource_id: Optional[str] = None,
        content_description: Optional[str] = None,
        class_name: Optional[str] = None,
        hint: Optional[str] = None,
        text_contains: Optional[str] = None,
        index: int = 0,
        timeout: Optional[float] = None,
    ) -> ActionResponse:
        selector = Selector(text, resource_id, content_description, class_name, hint, text_contains)
        self.require_selector(selector)
        _, matches = self.locate(selector, timeout)
        target = selector.describe()
        if not matches or index < 0 or index >= len(matches):
            details = f"No element matching {selector.describe_str()} was found"
            if matches:
                details = f"Only {len(matches)} element(s) matched {selector.describe_str()}; index {index} is out of range"
            return ActionResponse.fail(
                "find_element", ErrorCode.ELEMENT_NOT_FOUND, "Element not found", details,
                {"target": target, "match_count": len(matches)},
            )
        return ActionResponse.ok(
            "find_element",
            "Element found",
            {"target": target, "match_count": len(matches), "element": matches[index].to_dict()},
        )

    @guarded("element_exists")
    def element_exists(
        self,
        text: Optional[str] = None,
        resource_id: Optional[str] = None,
        content_description: Optional[str] = None,
        class_name: Optional[str] = None,
        hint: Optional[str] = None,
        text_contains: Optional[str] = None,
        timeout: Optional[float] = 0,
    ) -> ActionResponse:
        """``success`` means the query ran; the answer is in ``data['exists']``."""
        selector = Selector(text, resource_id, content_description, class_name, hint, text_contains)
        self.require_selector(selector)
        _, matches = self.locate(selector, timeout)
        exists = bool(matches)
        return ActionResponse.ok(
            "element_exists",
            "Element exists" if exists else "Element does not exist",
            {"target": selector.describe(), "exists": exists, "match_count": len(matches)},
        )
