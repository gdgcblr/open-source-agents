"""The agent-under-test contract. Implement `Target` to plug in any agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ToolEndpoint:
    """How the target reaches the murphy proxy (an MCP server over stdio)."""

    command: str
    args: list[str]
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None


@dataclass
class TargetReply:
    text: str
    tokens: int = 0


class Target(Protocol):
    label: str

    async def start(self, tools: ToolEndpoint | None) -> None:
        """Connect the agent's tools to `tools` (None when the config declares no MCP upstreams)."""

    async def send(self, message: str) -> TargetReply: ...

    async def close(self) -> None: ...
