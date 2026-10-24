"""Tests for agent behavioral logic, guardrails, and anti-hallucination policies."""

import pytest
from unittest.mock import MagicMock, patch
from goalflow import db, tools
from goalflow.agent import GOALFLOW_SYSTEM_INSTRUCTION, create_agent
from goalflow.models import GoalLevel, GoalStatus


@pytest.fixture(autouse=True)
def set_test_db(temp_db, monkeypatch):
    """Ensure tests run against isolated test database."""
    monkeypatch.setenv("GOALFLOW_DB_PATH", temp_db)


def test_agent_initialization():
    """Verify that ADK Agent initializes with full tool suite and instructions."""
    agent = create_agent(model="gemini-2.0-flash")
    assert agent.name == "goalflow_agent"
    assert agent.model == "gemini-2.0-flash"
    assert len(agent.tools) == 7
    # Ensure guardrail instructions exist
    assert "DO NOT mark a goal as completed unless the user explicitly confirms" in agent.instruction
    assert "NEVER invent achievements" in agent.instruction
    assert "retrieve_relevant_achievements" in agent.instruction


def test_self_doubt_retrieval_with_saved_achievements():
    """Verify retrieval of actual achievements when self-doubt is triggered."""
    # Seed the database with 2 real achievements
    db.create_achievement(
        title="Completed Python 3.11 environment setup",
        category="learning",
        milestone_date="2026-10-23",
        notes="Understood ADK architecture",
    )
    db.create_achievement(
        title="Created first SQLite goal schema",
        category="engineering",
        milestone_date="2026-10-24",
    )

    # Tool execution simulates what agent calls on user saying 'I feel like I have not achieved anything'
    result = tools.retrieve_relevant_achievements(limit=5)
    assert result["status"] == "success"
    assert result["count"] == 2

    titles = [a["title"] for a in result["achievements"]]
    assert "Completed Python 3.11 environment setup" in titles
    assert "Created first SQLite goal schema" in titles


def test_self_doubt_retrieval_with_empty_history():
    """Verify that empty achievement history returns 0 and does not fabricate data."""
    result = tools.retrieve_relevant_achievements(limit=5)
    assert result["status"] == "success"
    assert result["count"] == 0
    assert result["achievements"] == []


def test_reflection_does_not_prematurely_complete_goals():
    """Guardrail: Ensure logging a reflection does not mark a goal as completed."""
    goal = db.create_goal(title="Read chapter 4 of Agent Design", level=GoalLevel.DAILY, category="learning")
    assert goal.status == GoalStatus.PENDING

    # User reflects that they intended or worked on it, but didn't finish
    ref_res = tools.record_daily_reflection(
        raw_text="Today I started reading chapter 4 but got distracted by notifications and didn't finish.",
        summary="Started chapter 4, distracted before completion.",
        completed_items="",
        blockers="Notifications",
        next_day_priority="Finish chapter 4 in a focused 25-minute block.",
    )
    assert ref_res["status"] == "success"

    # Goal must remain PENDING
    refreshed_goal = db.get_goal(goal.id)
    assert refreshed_goal.status == GoalStatus.PENDING


def test_mocked_agent_chat_stream():
    """Test the agent chat wrapper with mocked ADK runner (0 API calls)."""
    from goalflow.agent import GoalFlowAgentService
    from google.genai import types

    service = GoalFlowAgentService(model="gemini-2.0-flash")

    # Mock runner.run_async to yield a mock event
    mock_event = MagicMock()
    mock_event.content = types.Content(
        role="model",
        parts=[types.Part(text="I checked your achievements. You completed your environment setup yesterday!")],
    )

    async def mock_run_async(*args, **kwargs):
        yield mock_event

    with patch.object(service.runner, "run_async", side_effect=mock_run_async):
        response = service.chat("I feel like I haven't done anything.")
        assert "You completed your environment setup yesterday!" in response


def test_command_suggestion_routing():
    """Verify that natural language inputs route to the correct CLI command."""
    from goalflow.cli import suggest_command

    assert suggest_command("yearly goals are create an ai gent") == "add-goal"
    assert suggest_command("Show me all my goals") == "list-goals"
    assert suggest_command("Today I worked on python and debugged code") == "reflect"
    assert suggest_command("I feel like I am falling behind and not improving") == "encourage"
    assert suggest_command("What is my goal completion rate and progress?") == "progress"
    assert suggest_command("Record a new milestone achievement") == "achievements"
    assert suggest_command("I want to check in today") == "check-in"
