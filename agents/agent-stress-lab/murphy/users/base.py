"""Simulated-user contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

Status = Literal["continue", "goal_met", "give_up"]


@dataclass
class UserTurn:
    message: str
    status: Status = "continue"
    tokens: int = 0


class User(Protocol):
    async def next(self, history: list[dict]) -> UserTurn:
        """history: [{"role": "user" | "agent", "text": str}, ...]"""
