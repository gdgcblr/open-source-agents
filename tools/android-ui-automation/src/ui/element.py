"""UI element model and selector matching."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


@dataclass(frozen=True)
class Bounds:
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> Tuple[int, int]:
        return (self.left + self.right) // 2, (self.top + self.bottom) // 2

    @classmethod
    def parse(cls, raw: str) -> "Bounds":
        m = _BOUNDS_RE.fullmatch(raw.strip()) if raw else None
        if not m:
            return cls()
        return cls(*(int(g) for g in m.groups()))


def _flag(node: ET.Element, key: str, default: bool = False) -> bool:
    value = node.get(key)
    return default if value is None else value == "true"


@dataclass
class Element:
    text: str = ""
    resource_id: str = ""
    content_description: str = ""
    class_name: str = ""
    package: str = ""
    hint: str = ""
    bounds: Bounds = field(default_factory=Bounds)
    clickable: bool = False
    long_clickable: bool = False
    enabled: bool = True
    focusable: bool = False
    focused: bool = False
    checkable: bool = False
    checked: bool = False
    selected: bool = False
    scrollable: bool = False
    password: bool = False
    visible_to_user: bool = True
    depth: int = 0
    order: int = 0
    parent: Optional["Element"] = field(default=None, repr=False, compare=False)

    @classmethod
    def from_xml(
        cls, node: ET.Element, parent: Optional["Element"], depth: int, order: int
    ) -> "Element":
        return cls(
            text=node.get("text", ""),
            resource_id=node.get("resource-id", ""),
            content_description=node.get("content-desc", ""),
            class_name=node.get("class", ""),
            package=node.get("package", ""),
            hint=node.get("hint", ""),
            bounds=Bounds.parse(node.get("bounds", "")),
            clickable=_flag(node, "clickable"),
            long_clickable=_flag(node, "long-clickable"),
            enabled=_flag(node, "enabled", True),
            focusable=_flag(node, "focusable"),
            focused=_flag(node, "focused"),
            checkable=_flag(node, "checkable"),
            checked=_flag(node, "checked"),
            selected=_flag(node, "selected"),
            scrollable=_flag(node, "scrollable"),
            password=_flag(node, "password"),
            visible_to_user=_flag(node, "visible-to-user", True),
            depth=depth,
            order=order,
            parent=parent,
        )

    @property
    def is_editable(self) -> bool:
        return "EditText" in self.class_name

    def has_clickable_ancestor(self) -> bool:
        p = self.parent
        while p is not None:
            if p.clickable:
                return True
            p = p.parent
        return False

    def to_dict(self) -> Dict[str, Any]:
        cx, cy = self.bounds.center
        b = self.bounds
        return {
            "text": self.text,
            "resource_id": self.resource_id,
            "content_description": self.content_description,
            "class_name": self.class_name,
            "package": self.package,
            "hint": self.hint,
            "bounds": [b.left, b.top, b.right, b.bottom],
            "center": [cx, cy],
            "clickable": self.clickable,
            "long_clickable": self.long_clickable,
            "enabled": self.enabled,
            "focusable": self.focusable,
            "focused": self.focused,
            "checkable": self.checkable,
            "checked": self.checked,
            "selected": self.selected,
            "scrollable": self.scrollable,
            "password": self.password,
            "visible_to_user": self.visible_to_user,
        }


@dataclass(frozen=True)
class Selector:
    """Criteria for locating an element. All provided criteria must match.

    * ``text`` / ``content_description``: exact, case-sensitive match.
    * ``text_contains``: substring match on text.
    * ``resource_id``: full id (``com.app:id/login``) or short id (``login``).
    * ``class_name``: full class or simple name (``EditText``).
    * ``hint``: hint attribute, or (for EditText) text equal to the hint.
    """

    text: Optional[str] = None
    resource_id: Optional[str] = None
    content_description: Optional[str] = None
    class_name: Optional[str] = None
    hint: Optional[str] = None
    text_contains: Optional[str] = None

    def describe(self) -> Dict[str, str]:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def describe_str(self) -> str:
        return ", ".join(f"{k}={v!r}" for k, v in self.describe().items())

    def is_empty(self) -> bool:
        return not self.describe()

    def matches(self, el: Element) -> bool:
        if self.text is not None and el.text != self.text:
            return False
        if self.text_contains is not None and self.text_contains not in el.text:
            return False
        if self.content_description is not None and el.content_description != self.content_description:
            return False
        if self.resource_id is not None:
            rid = self.resource_id
            if not (
                el.resource_id == rid
                or el.resource_id.endswith(":id/" + rid)
                or el.resource_id.endswith("/" + rid)
            ):
                return False
        if self.class_name is not None:
            cn = self.class_name
            if not (el.class_name == cn or el.class_name.endswith("." + cn)):
                return False
        if self.hint is not None:
            if not (el.hint == self.hint or (el.is_editable and el.text == self.hint)):
                return False
        return True
