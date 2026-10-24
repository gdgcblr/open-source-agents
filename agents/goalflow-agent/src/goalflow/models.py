"""Data models and enums for GoalFlow."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class GoalLevel(str, Enum):
    """Hierarchy levels for goals."""
    YEARLY = "yearly"
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    DAILY = "daily"

    @classmethod
    def from_str(cls, value: str) -> "GoalLevel":
        val = value.strip().lower()
        for member in cls:
            if member.value == val:
                return member
        raise ValueError(f"Invalid GoalLevel '{value}'. Allowed: {[m.value for m in cls]}")


class GoalStatus(str, Enum):
    """Status options for goals."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"

    @classmethod
    def from_str(cls, value: str) -> "GoalStatus":
        val = value.strip().lower()
        for member in cls:
            if member.value == val:
                return member
        raise ValueError(f"Invalid GoalStatus '{value}'. Allowed: {[m.value for m in cls]}")


@dataclass
class Goal:
    """Represents a goal in the hierarchy."""
    id: int
    title: str
    level: GoalLevel
    category: str
    parent_id: Optional[int]
    status: GoalStatus
    target_date: Optional[str]
    created_at: str
    updated_at: str


@dataclass
class Reflection:
    """Represents a recorded daily reflection."""
    id: int
    raw_text: str
    summary: str
    completed_notes: str
    blockers: str
    next_day_priority: str
    created_at: str


@dataclass
class Achievement:
    """Represents a verified milestone or achievement."""
    id: int
    title: str
    category: str
    goal_id: Optional[int]
    milestone_date: str
    notes: Optional[str]
    created_at: str


@dataclass
class CheckIn:
    """Represents a daily check-in event."""
    id: int
    check_in_date: str
    status: str
    created_at: str
