from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    name: str
    model: str

    def generate_json(self, prompt: str) -> dict: ...

    def generate_text(self, prompt: str) -> str: ...
