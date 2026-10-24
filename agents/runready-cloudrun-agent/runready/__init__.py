"""RunReady — safety-first Cloud Run deployment-rescue agent.

Exposes ``root_agent`` for ADK discovery (``adk web`` / ``adk run``).
"""

from . import agent  # noqa: F401  (ADK discovers `agent.root_agent`)
from .agent import root_agent  # noqa: F401

__all__ = ["agent", "root_agent"]
