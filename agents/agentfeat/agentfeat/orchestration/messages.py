"""Structured Agent-to-Agent message protocol for AgentFeat Hub-and-Spoke architecture."""

import time
import uuid
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """Supported task types routed through the Hub."""
    ANALYZE = "analyze_codebase"
    PLAN = "plan_feature"
    DEVELOP = "generate_code"
    QA = "validate_and_test"


class TaskStatus(str, Enum):
    """Status lifecycle of an agent task."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILURE = "failure"
    RETRYING = "retrying"


class AgentMessage(BaseModel):
    """Standardized message schema passed between the Hub and Spoke agents."""

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = Field(description="Unique identifier for the feature workflow run")
    sender: str = Field(description="Identifier of the sending agent (e.g., 'hub', 'analyzer')")
    recipient: str = Field(description="Identifier of the recipient agent (e.g., 'planner', 'hub')")
    task_type: TaskType = Field(description="Type of task being executed")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Execution status of this task")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Structured task payload")
    error: Optional[str] = Field(default=None, description="Error message if the task failed")
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of message creation")

    @classmethod
    def create_request(
        cls,
        task_id: str,
        sender: str,
        recipient: str,
        task_type: TaskType,
        payload: Dict[str, Any],
    ) -> "AgentMessage":
        """Factory helper to construct an outbound task request from Hub."""
        return cls(
            task_id=task_id,
            sender=sender,
            recipient=recipient,
            task_type=task_type,
            status=TaskStatus.PENDING,
            payload=payload,
        )

    @classmethod
    def create_response(
        cls,
        request: "AgentMessage",
        sender: str,
        payload: Dict[str, Any],
    ) -> "AgentMessage":
        """Factory helper for spoke agents to return successful task result."""
        return cls(
            task_id=request.task_id,
            sender=sender,
            recipient=request.sender,
            task_type=request.task_type,
            status=TaskStatus.SUCCESS,
            payload=payload,
        )

    @classmethod
    def create_error(
        cls,
        request: "AgentMessage",
        sender: str,
        error_msg: str,
    ) -> "AgentMessage":
        """Factory helper for spoke agents to return structured error message."""
        return cls(
            task_id=request.task_id,
            sender=sender,
            recipient=request.sender,
            task_type=request.task_type,
            status=TaskStatus.FAILURE,
            payload={},
            error=error_msg,
        )
