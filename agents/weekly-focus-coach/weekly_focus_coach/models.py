"""Validated data models shared by tools, storage, and future integrations."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Milestone(Model):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    title: str = Field(min_length=1, max_length=200)
    completed: bool = False
    completion_note: str = Field(default="", max_length=300)

    @field_validator("title", mode="before")
    @classmethod
    def trim_title(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class WeeklyGoal(Model):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    title: str = Field(min_length=1, max_length=120)
    week_start: date
    priority: int = Field(ge=1, le=2, strict=True)
    success_criteria: str = Field(min_length=1, max_length=500)
    metric_type: Literal["minutes", "milestones"]
    target_minutes: int | None = Field(default=None, gt=0, le=10080, strict=True)
    milestones: list[Milestone] = Field(default_factory=list, max_length=20)
    long_term_goal: str = Field(default="", max_length=500)
    target_date: date | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("title", "success_criteria", "long_term_goal", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("week_start")
    @classmethod
    def require_monday(cls, value: date) -> date:
        if value.weekday() != 0:
            raise ValueError("week_start must be a Monday")
        return value

    @model_validator(mode="after")
    def check_progress_measure(self) -> "WeeklyGoal":
        if self.metric_type == "minutes":
            if self.target_minutes is None or self.milestones:
                raise ValueError("Minute goals need a target and no milestones")
        elif self.target_minutes is not None or not self.milestones:
            raise ValueError("Milestone goals need milestones and no minute target")
        if len({milestone.id for milestone in self.milestones}) != len(self.milestones):
            raise ValueError("Milestone IDs must be unique within a goal")
        return self


class Activity(Model):
    id: str = Field(default_factory=lambda: uuid4().hex)
    activity_date: date
    description: str = Field(min_length=1, max_length=300)
    duration_minutes: int = Field(gt=0, le=1440, strict=True)
    day_period: Literal["morning", "afternoon", "evening"]
    goal_id: str | None = None
    accomplishment: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("description", "accomplishment", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class PlannedAction(Model):
    goal_id: str
    description: str = Field(min_length=1, max_length=300)
    duration_minutes: int = Field(gt=0, le=1440, strict=True)

    @field_validator("description", mode="before")
    @classmethod
    def trim_description(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class FocusPlan(Model):
    id: str = Field(default_factory=lambda: uuid4().hex)
    plan_date: date
    available_minutes: int = Field(ge=0, le=1440, strict=True)
    actions: list[PlannedAction] = Field(min_length=1, max_length=5)
    deferred_items: list[str] = Field(default_factory=list, max_length=10)
    adjustment_note: str = Field(default="", max_length=300)
    approved: Literal[True]
    approved_at: datetime = Field(default_factory=utc_now)

    @field_validator("deferred_items", "adjustment_note", mode="before")
    @classmethod
    def trim_text(cls, value: list[str] | str) -> list[str] | str:
        if isinstance(value, str):
            return value.strip()
        return [item.strip() for item in value]

    @model_validator(mode="after")
    def fit_available_time(self) -> "FocusPlan":
        if sum(action.duration_minutes for action in self.actions) > self.available_minutes:
            raise ValueError("Planned action time exceeds available time")
        return self


class FocusState(Model):
    schema_version: Literal[1] = 1
    revision: int = Field(default=0, ge=0, strict=True)
    goals: list[WeeklyGoal] = Field(default_factory=list)
    activities: list[Activity] = Field(default_factory=list)
    focus_plans: list[FocusPlan] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_links_and_limits(self) -> "FocusState":
        goal_ids = [goal.id for goal in self.goals]
        activity_ids = [activity.id for activity in self.activities]
        plan_ids = [plan.id for plan in self.focus_plans]
        for ids, label in ((goal_ids, "goal"), (activity_ids, "activity"), (plan_ids, "plan")):
            if len(ids) != len(set(ids)):
                raise ValueError(f"{label} IDs must be unique")

        counts: dict[date, int] = {}
        goals_by_id = {goal.id: goal for goal in self.goals}
        for goal in self.goals:
            counts[goal.week_start] = counts.get(goal.week_start, 0) + 1
        if any(count > 2 for count in counts.values()):
            raise ValueError("A week can have at most two goals")

        for activity in self.activities:
            if activity.goal_id:
                goal = goals_by_id.get(activity.goal_id)
                if not goal:
                    raise ValueError("Activity refers to an unknown goal")
                if not goal.week_start <= activity.activity_date < date.fromordinal(goal.week_start.toordinal() + 7):
                    raise ValueError("Activity date falls outside its goal week")

        for plan in self.focus_plans:
            if sum(action.duration_minutes for action in plan.actions) > plan.available_minutes:
                raise ValueError("Planned action time exceeds available time")
            for action in plan.actions:
                goal = goals_by_id.get(action.goal_id)
                if not goal or not goal.week_start <= plan.plan_date < date.fromordinal(goal.week_start.toordinal() + 7):
                    raise ValueError("Planned action refers to an unavailable goal")
        return self
