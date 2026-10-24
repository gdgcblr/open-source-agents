"""Tests for GoalFlow database operations and persistence."""

import pytest
from goalflow import db
from goalflow.models import GoalLevel, GoalStatus


def test_init_db(temp_db):
    """Test initializing the database tables."""
    goals = db.list_goals(db_path=temp_db)
    assert goals == []


def test_create_and_get_goal(temp_db):
    """Test creating and retrieving a goal."""
    goal = db.create_goal(
        title="Master Python Agent Development",
        level=GoalLevel.YEARLY,
        category="learning",
        target_date="2026-12-31",
        db_path=temp_db,
    )
    assert goal.id == 1
    assert goal.title == "Master Python Agent Development"
    assert goal.level == GoalLevel.YEARLY
    assert goal.status == GoalStatus.PENDING

    retrieved = db.get_goal(goal.id, db_path=temp_db)
    assert retrieved is not None
    assert retrieved.id == goal.id
    assert retrieved.title == goal.title


def test_goal_hierarchy(temp_db):
    """Test linking child goals to parent goals."""
    yearly = db.create_goal(title="Yearly: Run Marathon", level=GoalLevel.YEARLY, category="health", db_path=temp_db)
    monthly = db.create_goal(title="Monthly: Run 100km", level=GoalLevel.MONTHLY, category="health", parent_id=yearly.id, db_path=temp_db)
    weekly = db.create_goal(title="Weekly: Run 25km", level=GoalLevel.WEEKLY, category="health", parent_id=monthly.id, db_path=temp_db)
    daily = db.create_goal(title="Daily: 5km morning run", level=GoalLevel.DAILY, category="health", parent_id=weekly.id, db_path=temp_db)

    assert monthly.parent_id == yearly.id
    assert weekly.parent_id == monthly.id
    assert daily.parent_id == weekly.id

    subgoals = db.list_goals(parent_id=yearly.id, db_path=temp_db)
    assert len(subgoals) == 1
    assert subgoals[0].id == monthly.id


def test_persistence_across_reconnect(temp_db):
    """Verify that records persist across independent connection sessions."""
    goal = db.create_goal(title="Persist me", level=GoalLevel.DAILY, category="general", db_path=temp_db)
    ach = db.create_achievement(title="First victory", category="general", db_path=temp_db)
    ref = db.create_reflection(raw_text="Good day", summary="Productive", db_path=temp_db)

    # Re-access using a new connection query
    fetched_goal = db.get_goal(goal.id, db_path=temp_db)
    assert fetched_goal is not None
    assert fetched_goal.title == "Persist me"

    achievements = db.list_achievements(db_path=temp_db)
    assert len(achievements) == 1
    assert achievements[0].title == "First victory"

    reflections = db.list_reflections(db_path=temp_db)
    assert len(reflections) == 1
    assert reflections[0].summary == "Productive"


def test_update_goal_status(temp_db):
    """Test updating status of an existing goal."""
    goal = db.create_goal(title="Incomplete task", level=GoalLevel.DAILY, category="work", db_path=temp_db)
    assert goal.status == GoalStatus.PENDING

    updated = db.update_goal_status(goal.id, GoalStatus.IN_PROGRESS, db_path=temp_db)
    assert updated.status == GoalStatus.IN_PROGRESS

    completed = db.update_goal_status(goal.id, GoalStatus.COMPLETED, db_path=temp_db)
    assert completed.status == GoalStatus.COMPLETED


def test_invalid_inputs(temp_db):
    """Test input validations and database integrity protections."""
    # Empty title
    with pytest.raises(ValueError, match="title cannot be empty"):
        db.create_goal(title="", level=GoalLevel.DAILY, category="work", db_path=temp_db)

    # Invalid level
    with pytest.raises(ValueError, match="Invalid GoalLevel"):
        db.create_goal(title="Valid", level="decade", category="work", db_path=temp_db)

    # Non-existent parent_id
    with pytest.raises(ValueError, match="does not exist"):
        db.create_goal(title="Child with bad parent", level=GoalLevel.DAILY, category="work", parent_id=9999, db_path=temp_db)

    # Updating non-existent goal
    with pytest.raises(ValueError, match="not found"):
        db.update_goal_status(goal_id=9999, status=GoalStatus.COMPLETED, db_path=temp_db)


def test_check_in_recording(temp_db):
    """Test recording daily check-in."""
    assert db.get_latest_check_in(db_path=temp_db) is None
    c = db.record_check_in(check_in_date="2026-10-24", db_path=temp_db)
    assert c.check_in_date == "2026-10-24"
    assert c.status == "completed"

    latest = db.get_latest_check_in(db_path=temp_db)
    assert latest is not None
    assert latest.check_in_date == "2026-10-24"
