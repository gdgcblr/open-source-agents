"""LLM-free target for tests and demos: a policy coroutine decides which tools to call
on each turn, through the real proxy and upstreams."""

from __future__ import annotations

from typing import Awaitable, Callable

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from murphy.targets.base import TargetReply, ToolEndpoint

CallTool = Callable[[str, dict], Awaitable[tuple[bool, dict | str]]]
Policy = Callable[[int, str, CallTool], Awaitable[str]]


class ScriptedTarget:
    def __init__(self, policy: Policy, label: str = "scripted") -> None:
        self.policy = policy
        self.label = label
        self.turn = 0
        self._client: Client | None = None

    async def start(self, tools: ToolEndpoint | None) -> None:
        if tools is not None:
            self._client = Client(StdioTransport(tools.command, tools.args, env=tools.env, cwd=tools.cwd))
            await self._client.__aenter__()

    async def _call(self, tool: str, args: dict) -> tuple[bool, dict | str]:
        res = await self._client.call_tool(tool, args, raise_on_error=False)
        if res.is_error:
            return False, res.content[0].text if res.content else "error"
        return True, res.structured_content or {}

    async def send(self, message: str) -> TargetReply:
        self.turn += 1
        return TargetReply(await self.policy(self.turn, message, self._call))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._client = None
