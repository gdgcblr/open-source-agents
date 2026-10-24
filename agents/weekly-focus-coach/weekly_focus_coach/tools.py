"""ADK-callable operations for goal setting, check-ins, and focus plans."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import Activity, FocusPlan, FocusState, Milestone, PlannedAction, WeeklyGoal
from .storage import JsonStore


def _today() -> date:
    try:
        return datetime.now(ZoneInfo(os.environ.get("FOCUS_TIMEZONE", "UTC"))).date()
    except ZoneInfoNotFoundError as exc:
        raise ValueError("FOCUS_TIMEZONE must be a valid IANA timezone") from exc


def _week(value: str = "") -> date:
    try:
        start = date.fromisoformat(value) if value else _today() - timedelta(days=_today().weekday())
    except ValueError as exc:
        raise ValueError("week_start must be an ISO date such as 2026-10-19") from exc
    if start.weekday() != 0:
        raise ValueError("week_start must be a Monday")
    return start


def set_weekly_goal(
    title: str,
    priority: int,
    success_criteria: str,
    metric_type: Literal["minutes", "milestones"],
    target_minutes: int = 0,
    milestones: str = "",
    week_start: str = "",
    long_term_goal: str = "",
    target_date: str = "",
) -> dict[str, Any]:
    """Create a weekly goal; metric_type must be exactly minutes or milestones."""
    start = _week(week_start)
    titles = [part.strip() for part in milestones.split(";") if part.strip()]
    target_day = date.fromisoformat(target_date) if target_date else None
    kind = metric_type.strip().lower()
    if kind not in {"minutes", "milestones"}:
        raise ValueError("metric_type must be 'minutes' or 'milestones'")
    if kind == "minutes" and not target_minutes:
        raise ValueError("Minute goals require a positive target_minutes")
    if kind == "milestones" and not titles:
        raise ValueError("Milestone goals require one or more milestone titles separated by semicolons")
    goal = WeeklyGoal(
        title=title,
        priority=priority,
        success_criteria=success_criteria,
        week_start=start,
        metric_type=kind,
        target_minutes=target_minutes if kind == "minutes" else None,
        milestones=[Milestone(title=milestone) for milestone in titles] if kind == "milestones" else [],
        long_term_goal=long_term_goal,
        target_date=target_day,
    )
    def change(state: FocusState) -> None:
        if sum(g.week_start == start for g in state.goals) >= 2:
            raise ValueError("This week already has two goals")
        state.goals.append(goal)
    saved = JsonStore().update(change)
    return {"status": "success", "goal_id": goal.id, "goal": goal.model_dump(mode="json"), "revision": saved.revision}


def log_activity(
    description: str,
    duration_minutes: int,
    day_period: str,
    goal_id: str = "",
    accomplishment: str = "",
    activity_date: str = "",
) -> dict[str, Any]:
    """Log time and an accomplishment separately; link it to a goal when relevant."""
    day = date.fromisoformat(activity_date) if activity_date else _today()
    activity = Activity(
        description=description,
        duration_minutes=duration_minutes,
        day_period=day_period.strip().lower(),
        goal_id=goal_id.strip() or None,
        accomplishment=accomplishment,
        activity_date=day,
    )
    def change(state: FocusState) -> None:
        if day > _today():
            raise ValueError("Activities cannot be logged for a future date")
        if sum(item.duration_minutes for item in state.activities if item.activity_date == day) + duration_minutes > 1440:
            raise ValueError("Logged activity would exceed 24 hours for this date")
        state.activities.append(activity)
    JsonStore().update(change)
    return {"status": "success", "activity_id": activity.id, "duration_minutes": duration_minutes, "accomplishment": accomplishment.strip()}


def correct_activity(
    activity_id: str,
    description: str = "",
    duration_minutes: int = 0,
    day_period: str = "",
    accomplishment: str = "",
    activity_date: str = "",
) -> dict[str, Any]:
    """Correct an existing activity without adding a duplicate entry."""
    def change(state: FocusState) -> None:
        activity = next((item for item in state.activities if item.id == activity_id), None)
        if not activity:
            raise ValueError("Activity not found")
        updated = activity.model_copy(update={
            "description": description.strip() or activity.description,
            "duration_minutes": duration_minutes or activity.duration_minutes,
            "day_period": day_period.strip().lower() or activity.day_period,
            "accomplishment": accomplishment.strip() if accomplishment else activity.accomplishment,
            "activity_date": date.fromisoformat(activity_date) if activity_date else activity.activity_date,
        })
        if updated.activity_date > _today():
            raise ValueError("Activities cannot be logged for a future date")
        if sum(item.duration_minutes for item in state.activities if item.activity_date == updated.activity_date and item.id != activity_id) + updated.duration_minutes > 1440:
            raise ValueError("Corrected activity would exceed 24 hours for this date")
        state.activities[state.activities.index(activity)] = updated
    JsonStore().update(change)
    return {"status": "success", "activity_id": activity_id, "message": "Activity corrected; it was not duplicated."}


def update_goal_progress(goal_id: str, completed_milestone_ids: str, note: str) -> dict[str, Any]:
    """Set outcome progress to the reported completed milestone IDs; never infer it from time spent."""
    completed = {item.strip() for item in completed_milestone_ids.split(",") if item.strip()}
    if not note.strip():
        raise ValueError("Add a brief accomplishment note to support this progress update")
    def change(state: FocusState) -> None:
        goal = next((item for item in state.goals if item.id == goal_id), None)
        if not goal:
            raise ValueError("Goal not found")
        if goal.metric_type != "milestones":
            raise ValueError("This goal tracks time; log an activity to update its progress")
        valid = {milestone.id for milestone in goal.milestones}
        unknown = completed - valid
        if unknown:
            raise ValueError("Unknown milestone ID(s): " + ", ".join(sorted(unknown)))
        for milestone in goal.milestones:
            milestone.completed = milestone.id in completed
            milestone.completion_note = note.strip() if milestone.id in completed else ""
    saved = JsonStore().update(change)
    goal = next(item for item in saved.goals if item.id == goal_id)
    return {"status": "success", "goal_id": goal_id, "completed_milestones": sum(m.completed for m in goal.milestones), "total_milestones": len(goal.milestones), "note": note.strip()}


def get_weekly_metrics(week_start: str = "") -> dict[str, Any]:
    """Return separate per-goal bars for logged minutes and completed outcome milestones."""
    start = _week(week_start)
    end = start + timedelta(days=7)
    today = _today()
    state = JsonStore().load()
    results = []
    for goal in sorted((item for item in state.goals if item.week_start == start), key=lambda item: (item.priority, item.created_at)):
        minutes = sum(activity.duration_minutes for activity in state.activities if activity.goal_id == goal.id and start <= activity.activity_date < end)
        achieved = sum(milestone.completed for milestone in goal.milestones)
        if goal.metric_type == "minutes":
            numerator, denominator, unit = minutes, goal.target_minutes or 0, "minutes"
        else:
            numerator, denominator, unit = achieved, len(goal.milestones), "milestones"
        percent = min(100, round(numerator * 100 / denominator)) if denominator else 0
        results.append({
            "goal_id": goal.id,
            "title": goal.title,
            "priority": goal.priority,
            "success_criteria": goal.success_criteria,
            "long_term_goal": goal.long_term_goal,
            "target_date": goal.target_date.isoformat() if goal.target_date else None,
            "metric_type": goal.metric_type,
            "progress": {"completed": numerator, "target": denominator, "unit": unit, "percent": percent, "bar": "█" * round(percent / 10) + "░" * (10 - round(percent / 10))},
            "time_spent_minutes": minutes,
            "completed_milestones": [
                {"id": m.id, "title": m.title, "completed": m.completed, "completion_note": m.completion_note}
                for m in goal.milestones
            ],
        })
    activities = [item for item in state.activities if start <= item.activity_date < end]
    return {
        "status": "success", "week_start": start.isoformat(), "week_end_exclusive": end.isoformat(),
        "as_of_date": today.isoformat(),
        "days_elapsed": max(0, min(7, (today - start).days + 1)),
        "days_remaining": max(0, (end - today).days),
        "goals": results,
        "activities": [item.model_dump(mode="json") for item in activities],
        "focus_plans": [item.model_dump(mode="json") for item in state.focus_plans if start <= item.plan_date < end],
        "total_logged_minutes": sum(item.duration_minutes for item in activities),
        "completed_activity_count": len(activities), "revision": state.revision,
    }


def save_focus_plan(
    plan_date: str,
    goal_id: str,
    action: str,
    duration_minutes: int,
    available_minutes: int,
    approved: bool = False,
    deferred_items: str = "",
    adjustment_note: str = "",
) -> dict[str, Any]:
    """Save one user-approved focus action; ask the user before calling with approved=true."""
    if not approved:
        return {"status": "needs_confirmation", "message": "Ask the user whether to save this action. Do not change the plan yet."}
    plan = FocusPlan(
        plan_date=date.fromisoformat(plan_date),
        available_minutes=available_minutes,
        actions=[PlannedAction(goal_id=goal_id, description=action, duration_minutes=duration_minutes)],
        approved=True,
        deferred_items=[item.strip() for item in deferred_items.split(";") if item.strip()],
        adjustment_note=adjustment_note,
    )
    def change(state: FocusState) -> None:
        state.focus_plans.append(plan)
    JsonStore().update(change)
    return {"status": "success", "plan": plan.model_dump(mode="json"), "message": "Saved the user's selected plan."}
