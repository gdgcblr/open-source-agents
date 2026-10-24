"""Tests for ADK Agent Tools."""

import pytest
from goalflow import tools


@pytest.fixture(autouse=True)
def set_test_db_env(temp_db, monkeypatch):
    """Ensure tools talk to the isolated test database."""
    monkeypatch.setenv("GOALFLOW_DB_PATH", temp_db)


def test_tool_create_and_list_goals():
    """Test create_goal and list_goals tools."""
    res = tools.create_goal(
        title="Learn ADK Runners",
        level="weekly",
        category="learning",
        target_date="2026-10-31",
    )
    assert res["status"] == "success"
    assert "Created weekly goal" in res["message"]
    goal_id = res["goal"]["id"]

    list_res = tools.list_goals(level="weekly")
    assert list_res["status"] == "success"
    assert list_res["count"] == 1
    assert list_res["goals"][0]["id"] == goal_id


def test_tool_update_goal_status():
    """Test update_goal_status tool."""
    create_res = tools.create_goal(title="Read documentation", level="daily")
    gid = create_res["goal"]["id"]

    update_res = tools.update_goal_status(goal_id=gid, status="completed")
    assert update_res["status"] == "success"
    assert update_res["goal"]["status"] == "completed"


def test_tool_record_daily_reflection():
    """Test record_daily_reflection tool."""
    res = tools.record_daily_reflection(
        raw_text="Today I wrote tests and finished the agent tools.",
        summary="Focused on test-driven development.",
        completed_items="Built tests for tools.",
        blockers="None",
        next_day_priority="Wire up CLI and finish README.",
    )
    assert res["status"] == "success"
    assert "Reflection #" in res["message"]


def test_tool_record_and_retrieve_achievements():
    """Test recording and retrieving achievements."""
    # Before adding achievements
    empty_res = tools.retrieve_relevant_achievements()
    assert empty_res["status"] == "success"
    assert empty_res["count"] == 0
    assert empty_res["achievements"] == []

    # Record an achievement
    rec_res = tools.record_achievement(
        title="Deployed first Google ADK agent",
        category="career",
        notes="High confidence in agent architecture",
    )
    assert rec_res["status"] == "success"

    # Retrieve again
    fetched = tools.retrieve_relevant_achievements()
    assert fetched["status"] == "success"
    assert fetched["count"] == 1
    assert fetched["achievements"][0]["title"] == "Deployed first Google ADK agent"


def test_tool_get_progress_summary():
    """Test get_progress_summary tool."""
    tools.create_goal(title="Test goal", level="daily")
    res = tools.get_progress_summary(timeframe="today")
    assert res["status"] == "success"
    assert "progress" in res
    assert res["progress"]["daily_rate"] == 0.0
