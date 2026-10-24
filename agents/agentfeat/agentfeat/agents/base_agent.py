"""Base class for all spoke agents in the Hub-and-Spoke system."""

import abc
import logging
from typing import Optional

from agentfeat.orchestration.messages import AgentMessage

logger = logging.getLogger(__name__)


class BaseAgent(abc.ABC):
    """Abstract base class for all specialized spoke agents."""

    def __init__(self, name: str, role: str) -> None:
        self.name = name
        self.role = role

    def execute(self, message: AgentMessage) -> AgentMessage:
        """Entrypoint for task execution. Handles errors and ensures message contract."""
        if message.recipient != self.name and message.recipient != "*":
            return AgentMessage.create_error(
                message,
                sender=self.name,
                error_msg=f"Message misrouted: expected recipient '{self.name}', got '{message.recipient}'",
            )

        try:
            return self.process(message)
        except Exception as e:
            logger.error(f"Agent '{self.name}' failed to process task {message.task_id}: {e}", exc_info=True)
            return AgentMessage.create_error(
                message,
                sender=self.name,
                error_msg=f"Execution error in {self.name}: {str(e)}",
            )

    @abc.abstractmethod
    def process(self, message: AgentMessage) -> AgentMessage:
        """Process incoming task message and return a response message."""
        raise NotImplementedError
