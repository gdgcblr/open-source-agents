"""
Workshop Troubleshooter Agent Package.
Exports root_agent for Google ADK runtime discovery.
"""

from .agent import root_agent
from . import agent as agent

__all__ = ["root_agent", "agent"]
