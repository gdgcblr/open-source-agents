"""Enterprise integration tests for Multi-Agent Orchestrator and Circuit Breakers."""

import os
import shutil
import pytest

from team.exceptions import InvalidTopicError
from team.orchestrator import EditorialOrchestrator
from team.tools.reporter import export_publication_artifacts
from mcp_server import create_mcp_server

TEST_DIR = "test_multi_agent_tmp"


@pytest.fixture(autouse=True)
def cleanup():
    """Cleans up temporary artifacts before and after tests."""
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR, ignore_errors=True)
    yield
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR, ignore_errors=True)


def test_full_pipeline_mock_execution():
    """Validates complete collaborative flow: Plan -> Research -> Draft v1 -> Revise -> Draft v2 -> Approved."""
    events = []

    def callback(event):
        events.append(event)

    orchestrator = EditorialOrchestrator(
        mock_mode=True,
        max_revisions=2,
        pass_score=85,
        event_callback=callback
    )

    state = orchestrator.run("Multi-Agent Collaborative Workflows")

    # Assertions on pipeline state
    assert state.is_approved is True
    assert state.revision_turns == 1
    assert len(state.draft_history) == 2  # v1 and v2
    assert len(state.verdict_history) == 2  # verdict 1 (revise) and verdict 2 (approved)
    assert len(state.messages) >= 5
    assert len(state.evidence) >= 1
    assert state.plan is not None

    # Assertions on telemetry metrics
    metrics = state.metrics
    assert metrics is not None
    assert metrics.status == "approved"
    assert metrics.final_score >= 85
    assert metrics.duration_seconds >= 0.0
    assert metrics.revision_count == 1
    assert len(events) >= 6


def test_circuit_breaker_max_revisions_limit():
    """Validates that circuit breaker halts infinite loops when max revisions limit is reached."""
    # Setting max_revisions=1 so after 1 revision turn, loop halts regardless of score
    orchestrator = EditorialOrchestrator(
        mock_mode=True,
        max_revisions=1,
        pass_score=99,  # Impossibly high score forcing REVISE
    )

    state = orchestrator.run("Circuit Breaker Test Topic")

    assert state.revision_turns == 1
    assert state.metrics.status == "best_effort_published"
    assert state.is_approved is False


def test_empty_topic_raises_invalid_topic_error():
    """Validates that empty or whitespace topics raise InvalidTopicError."""
    orchestrator = EditorialOrchestrator(mock_mode=True)
    with pytest.raises(InvalidTopicError):
        orchestrator.run("")
    with pytest.raises(InvalidTopicError):
        orchestrator.run("   ")
    with pytest.raises(InvalidTopicError):
        orchestrator.run(None)


def test_publication_export_dual_artifacts():
    """Validates that export_publication_artifacts generates both .md and .html files."""
    orchestrator = EditorialOrchestrator(mock_mode=True, max_revisions=2)
    state = orchestrator.run("Publication Export Verification")

    artifacts = export_publication_artifacts(state, output_dir=TEST_DIR)

    assert "markdown_path" in artifacts
    assert "html_path" in artifacts
    assert os.path.exists(artifacts["markdown_path"])
    assert os.path.exists(artifacts["html_path"])

    with open(artifacts["markdown_path"], "r", encoding="utf-8") as f:
        md_text = f.read()
    assert "quality_score:" in md_text
    assert "revisions_applied:" in md_text

    with open(artifacts["html_path"], "r", encoding="utf-8") as f:
        html_text = f.read()
    assert "<!DOCTYPE html>" in html_text
    assert "Publication Export Verification" in html_text
    assert "Collaborative Agent Flow" in html_text


def test_mcp_server_bindings():
    """Validates that FastMCP server configures the editorial team tool."""
    server = create_mcp_server()
    assert server is not None
    assert server.name == "EditorialTeam"
