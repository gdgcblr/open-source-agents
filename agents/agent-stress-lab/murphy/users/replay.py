"""Replays recorded user turns verbatim (with their recorded status), then hands over to a fallback."""

from __future__ import annotations

from murphy.users.base import User, UserTurn


class ReplayUser:
    def __init__(self, turns: list[UserTurn], fallback: User | None) -> None:
        self.turns = turns
        self.fallback = fallback
        self.i = 0
        self.diverged = False

    async def next(self, history: list[dict]) -> UserTurn:
        if self.i < len(self.turns):
            self.i += 1
            return self.turns[self.i - 1]
        self.diverged = True
        if self.fallback is None:
            return UserTurn("", "give_up")
        return await self.fallback.next(history)
