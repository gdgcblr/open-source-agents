"""Google ADK agent package for LifeAdmin."""

from importlib import import_module
from typing import Any


def __getattr__(name: str) -> Any:
    if name == "root_agent":
        return import_module(".agent", __name__).root_agent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
