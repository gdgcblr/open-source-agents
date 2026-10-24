"""You are the user: messages are typed in the terminal (`murphy chat`)."""

from __future__ import annotations

import asyncio
from typing import Callable

from murphy.users.base import UserTurn

COMMANDS = {"/done": "goal_met", "/quit": "give_up"}
HELP = "type a message · /done when your goal is met · /quit to give up"


class HumanUser:
    def __init__(self, read: Callable[[str], str] | None = None, prompt: str = "you › ") -> None:
        self.read = read or (lambda text: input(text))  # resolved per call, so tests can patch input()
        self.prompt = prompt

    async def next(self, history: list[dict]) -> UserTurn:
        while True:
            try:
                text = (await asyncio.to_thread(self.read, self.prompt)).strip()
            except (EOFError, KeyboardInterrupt):
                return UserTurn("", "give_up")
            if text.lower() in COMMANDS:
                return UserTurn("", COMMANDS[text.lower()])
            if text.startswith("/"):
                print(f"  ({HELP})")
                continue
            if text:
                return UserTurn(text)
