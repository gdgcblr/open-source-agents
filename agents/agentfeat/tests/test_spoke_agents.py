"""Unit tests for individual spoke agents."""

from pathlib import Path
import pytest

from agentfeat.agents.analyzer_agent import AnalyzerAgent
from agentfeat.agents.developer_agent import DeveloperAgent
from agentfeat.agents.planner_agent import PlannerAgent
from agentfeat.agents.qa_agent import QAAgent
from agentfeat.llm.gemini_client import GeminiClient
from agentfeat.models.schemas import CodebaseSummary, FeaturePlan, FileChange, PlanStep
from agentfeat.orchestration.messages import AgentMessage, TaskStatus, TaskType


def test_analyzer_agent(tmp_path: Path):
    (tmp_path / "app.py").write_text("print('hello')", encoding="utf-8")
    agent = AnalyzerAgent()

    msg = AgentMessage.create_request(
        task_id="t1",
        sender="hub",
        recipient="analyzer",
        task_type=TaskType.ANALYZE,
        payload={"target_dir": str(tmp_path), "query": "auth"},
    )
    resp = agent.execute(msg)

    assert resp.status == TaskStatus.SUCCESS
    assert "codebase_summary" in resp.payload
    assert resp.payload["codebase_summary"]["total_files"] == 1


def test_planner_agent():
    client = GeminiClient(offline=True)
    agent = PlannerAgent(client=client)

    summary = CodebaseSummary(
        root_path="/tmp",
        total_files=1,
        languages=["Python"],
    )

    msg = AgentMessage.create_request(
        task_id="t2",
        sender="hub",
        recipient="planner",
        task_type=TaskType.PLAN,
        payload={
            "feature_request": "Add logging middleware",
            "codebase_summary": summary.model_dump(),
        },
    )
    resp = agent.execute(msg)

    assert resp.status == TaskStatus.SUCCESS
    assert "plan" in resp.payload
    assert resp.payload["plan"]["feature_title"] is not None


def test_developer_agent_never_writes_to_disk(tmp_path: Path):
    client = GeminiClient(offline=True)
    agent = DeveloperAgent(client=client)

    plan = FeaturePlan(
        feature_title="Test Feature",
        summary="Test",
        architecture_notes="Notes",
        steps=[
            PlanStep(
                step_number=1,
                title="Create helper",
                action="create",
                target_file="helper.py",
                description="create helper",
            )
        ],
        new_dependencies=[],
        test_strategy="pytest",
        risk_assessment="None",
    )

    msg = AgentMessage.create_request(
        task_id="t3",
        sender="hub",
        recipient="developer",
        task_type=TaskType.DEVELOP,
        payload={
            "feature_request": "Create helper",
            "plan": plan.model_dump(),
            "target_dir": str(tmp_path),
        },
    )
    resp = agent.execute(msg)

    assert resp.status == TaskStatus.SUCCESS
    assert len(resp.payload["changes"]) == 1
    # Confirm helper.py was NOT written to disk by DeveloperAgent
    assert not (tmp_path / "helper.py").exists()


def test_qa_agent_validates_changes(tmp_path: Path):
    agent = QAAgent()

    valid_change = FileChange(
        file_path="valid.py",
        action="create",
        description="clean code",
        new_content="def add(a: int, b: int) -> int: return a + b\n",
    )
    invalid_change = FileChange(
        file_path="invalid.py",
        action="create",
        description="bad code",
        new_content="def broken(:\n",
    )

    msg = AgentMessage.create_request(
        task_id="t4",
        sender="hub",
        recipient="qa",
        task_type=TaskType.QA,
        payload={
            "changes": [valid_change.model_dump(), invalid_change.model_dump()],
            "target_dir": str(tmp_path),
        },
    )
    resp = agent.execute(msg)

    assert resp.status == TaskStatus.SUCCESS
    assert resp.payload["passed"] is False  # One change had syntax error
    assert any("broken" in f or "SyntaxError" in f for f in resp.payload["findings"])
