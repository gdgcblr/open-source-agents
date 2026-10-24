"""Plug-and-play: every pluggable slot takes a built-in name or an import path `module:attr`."""

from __future__ import annotations

import importlib
from typing import Any


def load(ref: str) -> Any:
    module, sep, attr = ref.partition(":")
    if not sep or not module or not attr:
        raise ValueError(f"expected an import path like 'package.module:name', got {ref!r}")
    obj = importlib.import_module(module)
    for part in attr.split("."):
        obj = getattr(obj, part)
    return obj


def is_import_path(ref: str) -> bool:
    return ":" in ref
