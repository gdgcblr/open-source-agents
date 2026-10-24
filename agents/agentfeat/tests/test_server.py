"""Tests for FastAPI backend server endpoints."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from agentfeat.web.server import app

client = TestClient(app)


def test_server_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "agentfeat"
    assert "gemini_configured" in data
    assert data["mode"] in ("live_gemini", "offline_mock")


def test_server_workflow_run_endpoint(tmp_path: Path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")

    payload = {
        "request": "Add logging middleware",
        "target_dir": str(tmp_path),
        "offline": True,
        "apply": False,
    }
    response = client.post("/api/workflow/run", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["task_id"].startswith("feat-")
    assert data["status"] == "review"
    assert data["mode"] == "offline_mock"
    assert data["plan"] is not None
    assert len(data["changes"]) > 0
    assert data["qa_passed"] is True
    assert len(data["audit_log"]) > 0
    assert "# Feature:" in data["pr_markdown"]


def test_server_workflow_run_invalid_target_dir():
    payload = {
        "request": "Add feature",
        "target_dir": "/non_existent_directory_9999",
        "offline": True,
    }
    response = client.post("/api/workflow/run", json=payload)
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


def test_server_serve_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "AgentFeat" in response.text
