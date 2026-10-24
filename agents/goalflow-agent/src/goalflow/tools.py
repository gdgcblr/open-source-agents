"""Tools exposed to the Google ADK Agent for GoalFlow.

All tools interact with the database and progress modules through strictly
typed, safe Python functions. The agent has no access to raw SQL execution.
"""

from typing import Any, Dict, List, Optional
from goalflow import db, progress
from goalflow.models import GoalLevel, GoalStatus


def create_goal(
    title: str,
    level: str,
    category: str = "general",
    parent_id: Optional[int] = None,
    target_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new goal in the hierarchy (yearly, monthly, weekly, daily).

    Args:
        title: Title/description of the goal.
        level: Hierarchy level ('yearly', 'monthly', 'weekly', 'daily').
        category: Category (e.g. 'career', 'health', 'learning', 'personal').
        parent_id: Optional ID of the parent goal to link this goal to.
        target_date: Optional target completion date formatted as 'YYYY-MM-DD'.

    Returns:
        A dictionary with the created goal's details or an error message.
    """
    try:
        goal = db.create_goal(
            title=title,
            level=level,
            category=category,
            parent_id=parent_id,
            target_date=target_date,
        )
        return {
            "status": "success",
            "message": f"Created {goal.level.value} goal #{goal.id}: '{goal.title}'",
            "goal": {
                "id": goal.id,
                "title": goal.title,
                "level": goal.level.value,
                "category": goal.category,
                "parent_id": goal.parent_id,
                "status": goal.status.value,
                "target_date": goal.target_date,
            },
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def list_goals(
    level: Optional[str] = None,
    status: Optional[str] = None,
    parent_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Retrieve existing goals, optionally filtered by level, status, or parent_id.

    Args:
        level: Optional level filter ('yearly', 'monthly', 'weekly', 'daily').
        status: Optional status filter ('pending', 'in_progress', 'completed', 'abandoned').
        parent_id: Optional parent goal ID to list sub-goals for.

    Returns:
        A dictionary containing the list of matching goals.
    """
    try:
        goals = db.list_goals(level=level, status=status, parent_id=parent_id)
        return {
            "status": "success",
            "count": len(goals),
            "goals": [
                {
                    "id": g.id,
                    "title": g.title,
                    "level": g.level.value,
                    "category": g.category,
                    "parent_id": g.parent_id,
                    "status": g.status.value,
                    "target_date": g.target_date,
                }
                for g in goals
            ],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def update_goal_status(goal_id: int, status: str) -> Dict[str, Any]:
    """Update the status of a specific goal.

    Args:
        goal_id: The ID of the goal to update.
        status: The new status ('pending', 'in_progress', 'completed', 'abandoned').

    Returns:
        A dictionary confirming the update or describing an error.
    """
    try:
        updated = db.update_goal_status(goal_id=goal_id, status=status)
        return {
            "status": "success",
            "message": f"Goal #{updated.id} status changed to {updated.status.value}",
            "goal": {
                "id": updated.id,
                "title": updated.title,
                "status": updated.status.value,
            },
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def record_daily_reflection(
    raw_text: str,
    summary: str,
    completed_items: str = "",
    blockers: str = "",
    next_day_priority: str = "",
) -> Dict[str, Any]:
    """Persist a daily reflection summary and identified key items.

    Args:
        raw_text: Original user reflection text.
        summary: Concise summary of what happened.
        completed_items: Notes on completed tasks or progress.
        blockers: Notes on obstacles or incomplete tasks.
        next_day_priority: One realistic focus or priority for tomorrow.

    Returns:
        A dictionary with the saved reflection ID and details.
    """
    try:
        ref = db.create_reflection(
            raw_text=raw_text,
            summary=summary,
            completed_notes=completed_items,
            blockers=blockers,
            next_day_priority=next_day_priority,
        )
        return {
            "status": "success",
            "message": f"Reflection #{ref.id} recorded successfully.",
            "reflection_id": ref.id,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def record_achievement(
    title: str,
    category: str = "general",
    goal_id: Optional[int] = None,
    milestone_date: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist a verified personal achievement, milestone, or learned skill.

    Args:
        title: Title of the achievement (e.g. 'Completed Module 1').
        category: Category ('career', 'learning', 'health', 'personal').
        goal_id: Optional ID of the related goal.
        milestone_date: Optional date of achievement ('YYYY-MM-DD'). Defaults to today.
        notes: Optional extra context or notes.

    Returns:
        A dictionary confirming the saved achievement.
    """
    try:
        ach = db.create_achievement(
            title=title,
            category=category,
            goal_id=goal_id,
            milestone_date=milestone_date,
            notes=notes,
        )
        return {
            "status": "success",
            "message": f"Achievement #{ach.id} recorded: '{ach.title}'",
            "achievement": {
                "id": ach.id,
                "title": ach.title,
                "category": ach.category,
                "milestone_date": ach.milestone_date,
            },
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def retrieve_relevant_achievements(
    category: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """Retrieve actual saved achievements and milestones from personal history.

    Use this tool whenever the user feels discouraged, expresses self-doubt,
    or asks what they have accomplished. Do NOT fabricate achievements; only
    cite items returned here.

    Args:
        category: Optional category to filter achievements.
        limit: Maximum number of achievements to return (defaults to 5).

    Returns:
        A dictionary with count and list of verified achievements.
    """
    try:
        achievements = db.list_achievements(category=category, limit=limit)
        return {
            "status": "success",
            "count": len(achievements),
            "achievements": [
                {
                    "id": a.id,
                    "title": a.title,
                    "category": a.category,
                    "milestone_date": a.milestone_date,
                    "notes": a.notes,
                }
                for a in achievements
            ],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_progress_summary(timeframe: str = "weekly") -> Dict[str, Any]:
    """Calculate and return deterministic progress statistics for a timeframe.

    Args:
        timeframe: 'today', 'weekly', 'monthly', or 'yearly'.

    Returns:
        A dictionary with completion percentages, counts, and stalled goals.
    """
    try:
        data = progress.get_progress_overview(timeframe=timeframe)
        return {"status": "success", "progress": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# List of all tools available to the ADK agent
GOALFLOW_TOOLS = [
    create_goal,
    list_goals,
    update_goal_status,
    record_daily_reflection,
    record_achievement,
    retrieve_relevant_achievements,
    get_progress_summary,
]
