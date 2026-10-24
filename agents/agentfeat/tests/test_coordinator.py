"""Unit tests for the central Hub (AgentCoordinator) and orchestration logic."""

from pathlib import Path
import pytest

from agentfeat.agents.base_agent import BaseAgent
from agentfeat.llm.gemini_client import GeminiClient
from agentfeat.orchestration.coordinator import AgentCoordinator
from agentfeat.orchestration.messages import AgentMessage, TaskStatus, TaskType
from agentfeat.orchestration.task_state import TaskState


class FailingAgent(BaseAgent):
    """Mock agent designed to simulate failures for testing retry bounds."""

    def __init__(self, failure_count: int = 10) -> None:
        super().__init__(name="failing_spoke", role="Failure Simulator")
        self.failure_count = failure_count
        self.call_count = 0

    def process(self, message: AgentMessage) -> AgentMessage:
        self.call_count += 1
        if self.call_count <= self.failure_count:
            return AgentMessage.create_error(
                message,
                sender=self.name,
                error_msg=f"Simulated failure attempt #{self.call_count}",
            )
        return AgentMessage.create_response(
            message,
            sender=self.name,
            payload={"status": "eventually_succeeded"},
        )


def test_coordinator_initialization():
    coordinator = AgentCoordinator(client=GeminiClient(offline=True))
    assert "analyzer" in coordinator.spokes
    assert "planner" in coordinator.spokes
    assert "developer" in coordinator.spokes
    assert "qa" in coordinator.spokes


def test_coordinator_workflow_execution(tmp_path: Path):
    (tmp_path / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("fastapi\npytest\n", encoding="utf-8")

    coordinator = AgentCoordinator(client=GeminiClient(offline=True))
    state = coordinator.run_workflow("Add health endpoint", tmp_path)

    assert state.current_stage == "review"
    assert state.codebase_summary is not None
    assert state.plan is not None
    assert len(state.changes) > 0
    assert state.qa_passed is True
    assert len(state.audit_log) > 0


def test_coordinator_routes_to_unknown_spoke():
    coordinator = AgentCoordinator(client=GeminiClient(offline=True))
    state = TaskState(feature_request="test", target_dir="/tmp")

    msg = AgentMessage.create_request(
        task_id=state.task_id,
        sender="hub",
        recipient="non_existent_spoke",
        task_type=TaskType.ANALYZE,
        payload={},
    )
    resp = coordinator.dispatch(msg, state)

    assert resp.status == TaskStatus.FAILURE
    assert "No spoke agent registered" in resp.error


def test_coordinator_bounded_retries():
    # Spoke fails 10 times, max_retries_per_agent is set to 2
    coordinator = AgentCoordinator(
        client=GeminiClient(offline=True),
        max_retries_per_agent=2,
    )
    failing_spoke = FailingAgent(failure_count=10)
    coordinator.register_spoke(failing_spoke)

    state = TaskState(feature_request="test", target_dir="/tmp")
    msg = AgentMessage.create_request(
        task_id=state.task_id,
        sender="hub",
        recipient="failing_spoke",
        task_type=TaskType.ANALYZE,
        payload={},
    )
    resp = coordinator.dispatch(msg, state)

    assert resp.status == TaskStatus.FAILURE
    # Should attempt initial run + 2 retries = 3 attempts total, then stop
    assert failing_spoke.call_count == 3
    assert state.get_retry_count("failing_spoke") == 2
