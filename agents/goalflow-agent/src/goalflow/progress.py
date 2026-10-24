"""Deterministic progress calculations and metrics for GoalFlow."""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from goalflow import db
from goalflow.models import Goal, GoalLevel, GoalStatus


def calculate_goal_progress(goal_id: int, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Calculate progress for a specific goal based on its children or status."""
    goal = db.get_goal(goal_id, db_path=db_path)
    if not goal:
        raise ValueError(f"Goal with ID {goal_id} not found.")

    children = db.list_goals(parent_id=goal_id, db_path=db_path)
    if not children:
        pct = 100.0 if goal.status == GoalStatus.COMPLETED else (50.0 if goal.status == GoalStatus.IN_PROGRESS else 0.0)
        return {
            "goal_id": goal.id,
            "title": goal.title,
            "level": goal.level.value,
            "status": goal.status.value,
            "total_subgoals": 0,
            "completed_subgoals": 0,
            "progress_percentage": pct,
        }

    total = len(children)
    completed = sum(1 for c in children if c.status == GoalStatus.COMPLETED)
    pct = round((completed / total) * 100.0, 1) if total > 0 else 0.0

    return {
        "goal_id": goal.id,
        "title": goal.title,
        "level": goal.level.value,
        "status": goal.status.value,
        "total_subgoals": total,
        "completed_subgoals": completed,
        "progress_percentage": pct,
    }


def get_level_summary(level: GoalLevel | str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Calculate progress statistics for a given goal hierarchy level."""
    g_level = level if isinstance(level, GoalLevel) else GoalLevel.from_str(level)
    goals = db.list_goals(level=g_level, db_path=db_path)

    total = len(goals)
    completed = sum(1 for g in goals if g.status == GoalStatus.COMPLETED)
    in_progress = sum(1 for g in goals if g.status == GoalStatus.IN_PROGRESS)
    pending = sum(1 for g in goals if g.status == GoalStatus.PENDING)
    abandoned = sum(1 for g in goals if g.status == GoalStatus.ABANDONED)

    completion_rate = round((completed / total) * 100.0, 1) if total > 0 else 0.0

    items = []
    for g in goals:
        sub_info = calculate_goal_progress(g.id, db_path=db_path)
        items.append({
            "id": g.id,
            "title": g.title,
            "status": g.status.value,
            "target_date": g.target_date,
            "subgoal_progress": f"{sub_info['completed_subgoals']}/{sub_info['total_subgoals']} ({sub_info['progress_percentage']}%)" if sub_info["total_subgoals"] > 0 else "N/A",
        })

    return {
        "level": g_level.value,
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "pending": pending,
        "abandoned": abandoned,
        "completion_rate": completion_rate,
        "goals": items,
    }


def get_stalled_goals(days_threshold: int = 7, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Identify goals in pending or in_progress status that haven't progressed recently."""
    all_goals = db.list_goals(db_path=db_path)
    now = datetime.now()
    threshold_dt = now - timedelta(days=days_threshold)

    stalled = []
    for g in all_goals:
        if g.status in (GoalStatus.PENDING, GoalStatus.IN_PROGRESS):
            updated_dt = datetime.fromisoformat(g.updated_at)
            is_inactive = updated_dt < threshold_dt
            is_overdue = False
            if g.target_date:
                try:
                    t_date = datetime.strptime(g.target_date, "%Y-%m-%d")
                    if t_date < now:
                        is_overdue = True
                except ValueError:
                    pass

            if is_inactive or is_overdue:
                days_since_update = (now - updated_dt).days
                stalled.append({
                    "id": g.id,
                    "title": g.title,
                    "level": g.level.value,
                    "status": g.status.value,
                    "days_inactive": days_since_update,
                    "is_overdue": is_overdue,
                    "target_date": g.target_date,
                })

    return stalled


def get_progress_overview(timeframe: str = "weekly", db_path: Optional[str] = None) -> Dict[str, Any]:
    """Compile structured progress data for today, weekly, monthly, or yearly reviews."""
    tf = timeframe.strip().lower()
    today_str = date.today().isoformat()

    days_back = 0
    if tf == "today":
        days_back = 0
    elif tf == "weekly":
        days_back = 7
    elif tf == "monthly":
        days_back = 30
    elif tf == "yearly":
        days_back = 365
    else:
        days_back = 7

    start_date = (date.today() - timedelta(days=days_back)).isoformat() if days_back > 0 else today_str

    all_achievements = db.list_achievements(db_path=db_path)
    period_achievements = [a for a in all_achievements if a.milestone_date >= start_date]

    all_reflections = db.list_reflections(limit=50, db_path=db_path)
    period_reflections = [r for r in all_reflections if r.created_at[:10] >= start_date]

    yearly_summary = get_level_summary(GoalLevel.YEARLY, db_path=db_path)
    monthly_summary = get_level_summary(GoalLevel.MONTHLY, db_path=db_path)
    weekly_summary = get_level_summary(GoalLevel.WEEKLY, db_path=db_path)
    daily_summary = get_level_summary(GoalLevel.DAILY, db_path=db_path)
    stalled = get_stalled_goals(days_threshold=7, db_path=db_path)

    return {
        "timeframe": tf,
        "start_date": start_date,
        "end_date": today_str,
        "achievements_count": len(period_achievements),
        "recent_achievements": [a.title for a in period_achievements[:5]],
        "reflections_count": len(period_reflections),
        "yearly_rate": yearly_summary["completion_rate"],
        "monthly_rate": monthly_summary["completion_rate"],
        "weekly_rate": weekly_summary["completion_rate"],
        "daily_rate": daily_summary["completion_rate"],
        "stalled_goals_count": len(stalled),
        "stalled_goals": stalled[:5],
    }
