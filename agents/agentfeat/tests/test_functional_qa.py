"""Functional QA tests verifying real endpoint generation, TestClient testing, and failure detection."""

from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentfeat.agents.qa_agent import QAAgent
from agentfeat.llm.gemini_client import GeminiClient
from agentfeat.models.schemas import CodebaseSummary, FeaturePlan, FileChange
from agentfeat.orchestration.coordinator import AgentCoordinator


def test_real_fastapi_healthcheck_generation(tmp_path: Path):
    """Verify that a health-check feature on a FastAPI app generates a real GET /health route and TestClient test."""
    # 1. Setup disposable FastAPI sample app
    main_file = tmp_path / "main.py"
    main_file.write_text(
        "from fastapi import FastAPI\n\n"
        "app = FastAPI()\n\n"
        "@app.get('/')\n"
        "def root():\n"
        "    return {'message': 'Hello World'}\n",
        encoding="utf-8"
    )
    (tmp_path / "requirements.txt").write_text("fastapi\npytest\n", encoding="utf-8")

    # 2. Run workflow through coordinator
    coordinator = AgentCoordinator(client=GeminiClient(offline=True))
    state = coordinator.run_workflow("Add a health-check endpoint", tmp_path)

    assert state.current_stage == "review"
    assert state.plan.feature_title == "Health Check Endpoint"

    # Verify changes target main.py and tests/test_health.py
    change_files = [c.file_path for c in state.changes]
    assert "main.py" in change_files
    assert "tests/test_health.py" in change_files

    # Verify modified main.py contains real @app.get('/health')
    main_change = next(c for c in state.changes if c.file_path == "main.py")
    assert "@app.get(\"/health\")" in main_change.new_content

    # Verify test file imports TestClient and app
    test_change = next(c for c in state.changes if c.file_path == "tests/test_health.py")
    assert "from fastapi.testclient import TestClient" in test_change.new_content
    assert "client.get(\"/health\")" in test_change.new_content

    # Verify QA gate executed genuine tests and passed
    assert state.qa_passed is True
    assert any("Dynamic QA Gate PASSED" in f for f in state.qa_findings)


def test_qa_fails_when_endpoint_is_broken(tmp_path: Path):
    """Verify that QAAgent fails when the test asserts an endpoint that does NOT exist in the code."""
    agent = QAAgent()

    # Code without health endpoint
    broken_code = (
        "from fastapi import FastAPI\n\n"
        "app = FastAPI()\n\n"
        "@app.get('/other')\n"
        "def other():\n"
        "    return {'status': 'other'}\n"
    )

    # Test asserting non-existent /health route (will return 404 and fail assertion)
    failing_test = (
        "from fastapi.testclient import TestClient\n"
        "from main import app\n\n"
        "client = TestClient(app)\n\n"
        "def test_missing_endpoint():\n"
        "    response = client.get('/health')\n"
        "    assert response.status_code == 200\n"
    )

    changes = [
        FileChange(
            file_path="main.py",
            action="create",
            description="app without health endpoint",
            new_content=broken_code,
        ),
        FileChange(
            file_path="tests/test_failing.py",
            action="create",
            description="test that should fail",
            new_content=failing_test,
        ),
    ]

    msg_payload = {
        "changes": [c.model_dump() for c in changes],
        "target_dir": str(tmp_path),
    }

    from agentfeat.orchestration.messages import AgentMessage, TaskType
    req = AgentMessage.create_request("t_broken", "hub", "qa", TaskType.QA, msg_payload)
    resp = agent.execute(req)

    # QA gate MUST fail
    assert resp.payload["passed"] is False
    assert resp.payload["test_execution_passed"] is False
    assert any("Dynamic QA Gate FAILED" in f for f in resp.payload["findings"])
