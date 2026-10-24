"""AgentFeat: AI-powered feature development agent (Hub-and-Spoke Multi-Agent Architecture).

From feature request to working code, with AI.
"""

from .orchestration.coordinator import AgentCoordinator
from .orchestration.messages import AgentMessage

__version__ = "0.2.0"

__all__ = [
    "AgentCoordinator",
    "AgentMessage",
]
