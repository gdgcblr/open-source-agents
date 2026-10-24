"""State management, workflow tracking, and audit logging for the Hub."""

import time
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agentfeat.models.schemas import CodebaseSummary, FeaturePlan, FileChange


class AuditEntry(BaseModel):
    """Immutable audit record for workflow events."""
    timestamp: float = Field(default_factory=time.time)
    stage: str
    agent: str
    event: str
    details: Dict[str, Any] = Field(default_factory=dict)


class TaskState(BaseModel):
    """Centralized shared state maintained exclusively by the Hub (AgentCoordinator)."""

    task_id: str = Field(default_factory=lambda: f"feat-{uuid.uuid4().hex[:8]}")
    feature_request: str = Field(description="The user's original feature prompt")
    target_dir: str = Field(description="Target workspace repository path")
    current_stage: str = Field(default="init", description="Current stage in workflow")
    retry_counts: Dict[str, int] = Field(default_factory=dict, description="Retries attempted per agent")

    # Spoke Artifacts
    codebase_summary: Optional[CodebaseSummary] = None
    plan: Optional[FeaturePlan] = None
    changes: List[FileChange] = Field(default_factory=list)
    qa_passed: bool = False
    qa_findings: List[str] = Field(default_factory=list)
    applied: bool = False

    # Audit Trail
    audit_log: List[AuditEntry] = Field(default_factory=list)

    def log(self, stage: str, agent: str, event: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Record an immutable event in the audit trail."""
        self.audit_log.append(
            AuditEntry(
                stage=stage,
                agent=agent,
                event=event,
                details=details or {},
            )
        )

    def get_retry_count(self, agent: str) -> int:
        """Get number of retries already executed by an agent."""
        return self.retry_counts.get(agent, 0)

    def increment_retry(self, agent: str) -> int:
        """Increment and return retry count for an agent."""
        count = self.retry_counts.get(agent, 0) + 1
        self.retry_counts[agent] = count
        return count

    def can_retry(self, agent: str, max_retries: int = 2) -> bool:
        """Determine whether an agent has exceeded its allowed retry quota."""
        return self.get_retry_count(agent) < max_retries
