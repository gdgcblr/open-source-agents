"""Tests for deterministic progress calculations and stalled goal alerts."""

from datetime import datetime, timedelta
import pytest
from goalflow import db, progress
from goalflow.models import GoalLevel, GoalStatus


def test_goal_progress_without_subgoals(temp_db):
    """Test progress calculation for a leaf goal."""
    goal = db.create_goal(title="Read a paper", level=GoalLevel.DAILY, category="learning", db_path=temp_db)
    res = progress.calculate_goal_progress(goal.id, db_path=temp_db)
    assert res["progress_percentage"] == 0.0

    db.update_goal_status(goal.id, GoalStatus.IN_PROGRESS, db_path=temp_db)
    res = progress.calculate_goal_progress(goal.id, db_path=temp_db)
    assert res["progress_percentage"] == 50.0

    db.update_goal_status(goal.id, GoalStatus.COMPLETED, db_path=temp_db)
    res = progress.calculate_goal_progress(goal.id, db_path=temp_db)
    assert res["progress_percentage"] == 100.0


def test_goal_progress_with_subgoals(temp_db):
    """Test progress rollup for parent goal with multiple child goals."""
    parent = db.create_goal(title="Learn Google ADK", level=GoalLevel.MONTHLY, category="learning", db_path=temp_db)

    sub1 = db.create_goal(title="Chapter 1", level=GoalLevel.WEEKLY, category="learning", parent_id=parent.id, db_path=temp_db)
    sub2 = db.create_goal(title="Chapter 2", level=GoalLevel.WEEKLY, category="learning", parent_id=parent.id, db_path=temp_db)
    sub3 = db.create_goal(title="Chapter 3", level=GoalLevel.WEEKLY, category="learning", parent_id=parent.id, db_path=temp_db)
    sub4 = db.create_goal(title="Chapter 4", level=GoalLevel.WEEKLY, category="learning", parent_id=parent.id, db_path=temp_db)

    # 0 completed
    res = progress.calculate_goal_progress(parent.id, db_path=temp_db)
    assert res["total_subgoals"] == 4
    assert res["completed_subgoals"] == 0
    assert res["progress_percentage"] == 0.0

    # 1 completed (1/4 = 25%)
    db.update_goal_status(sub1.id, GoalStatus.COMPLETED, db_path=temp_db)
    res = progress.calculate_goal_progress(parent.id, db_path=temp_db)
    assert res["completed_subgoals"] == 1
    assert res["progress_percentage"] == 25.0

    # 2 completed (2/4 = 50%)
    db.update_goal_status(sub2.id, GoalStatus.COMPLETED, db_path=temp_db)
    res = progress.calculate_goal_progress(parent.id, db_path=temp_db)
    assert res["completed_subgoals"] == 2
    assert res["progress_percentage"] == 50.0


def test_level_summary(temp_db):
    """Test level summary metrics across goals."""
    db.create_goal(title="Goal 1", level=GoalLevel.DAILY, category="work", db_path=temp_db)
    g2 = db.create_goal(title="Goal 2", level=GoalLevel.DAILY, category="work", db_path=temp_db)
    db.update_goal_status(g2.id, GoalStatus.COMPLETED, db_path=temp_db)

    summary = progress.get_level_summary(GoalLevel.DAILY, db_path=temp_db)
    assert summary["total"] == 2
    assert summary["completed"] == 1
    assert summary["pending"] == 1
    assert summary["completion_rate"] == 50.0


def test_stalled_goals_detection(temp_db):
    """Test detection of stalled or overdue goals."""
    # Active goal created right now
    fresh_goal = db.create_goal(title="Fresh goal", level=GoalLevel.DAILY, category="work", db_path=temp_db)

    # Overdue goal
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    overdue_goal = db.create_goal(title="Overdue task", level=GoalLevel.DAILY, category="work", target_date=yesterday, db_path=temp_db)

    stalled = progress.get_stalled_goals(days_threshold=7, db_path=temp_db)
    stalled_ids = [s["id"] for s in stalled]

    assert fresh_goal.id not in stalled_ids
    assert overdue_goal.id in stalled_ids
