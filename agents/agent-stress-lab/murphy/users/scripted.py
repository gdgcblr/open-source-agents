"""Fixed user messages (tests, smoke runs, CI without a model)."""

from __future__ import annotations

from murphy.users.base import Status, UserTurn


class ScriptedUser:
    def __init__(self, messages: list[str], final_status: Status = "goal_met") -> None:
        self.messages = list(messages)
        self.final_status = final_status
        self.i = 0

    async def next(self, history: list[dict]) -> UserTurn:
        if self.i >= len(self.messages):
            return UserTurn("", self.final_status)
        self.i += 1
        return UserTurn(self.messages[self.i - 1])
