"""TraceTriage package with lazy ADK import (offline mode needs no dependencies)."""


def __getattr__(name: str):
    if name == "root_agent":
        from .agent import root_agent
        return root_agent
    raise AttributeError(name)
