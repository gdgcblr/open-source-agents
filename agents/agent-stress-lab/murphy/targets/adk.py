"""Google ADK adapter. The agent's tools come from an McpToolset that launches the
murphy proxy, so every tool call goes through faults, policies and recording."""

from __future__ import annotations

import inspect
from typing import Any, Callable

from google.adk.runners import InMemoryRunner
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from google.genai import types
from mcp import StdioServerParameters

from murphy.targets.base import TargetReply, ToolEndpoint

APP = "murphy"
USER = "simulated-user"


class AdkTarget:
    def __init__(self, factory: Callable[..., Any], label: str, model: str | None = None) -> None:
        self.factory = factory
        self.label = label
        self.model = model
        self._toolset: McpToolset | None = None
        self._runner: InMemoryRunner | None = None
        self._session_id = ""

    def _build_agent(self, toolset):
        kwargs = {}
        if self.model and "model" in inspect.signature(self.factory).parameters:
            kwargs["model"] = self.model
        return self.factory(toolset, **kwargs)

    async def start(self, tools: ToolEndpoint | None) -> None:
        if tools is not None:
            self._toolset = McpToolset(connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(command=tools.command, args=tools.args, env=tools.env, cwd=tools.cwd),
                timeout=30,
            ))
        self._runner = InMemoryRunner(agent=self._build_agent(self._toolset), app_name=APP)
        session = await self._runner.session_service.create_session(app_name=APP, user_id=USER)
        self._session_id = session.id

    async def send(self, message: str) -> TargetReply:
        content = types.Content(role="user", parts=[types.Part(text=message)])
        texts: list[str] = []
        tokens = 0
        async for event in self._runner.run_async(user_id=USER, session_id=self._session_id, new_message=content):
            if event.usage_metadata and event.usage_metadata.total_token_count:
                tokens += event.usage_metadata.total_token_count
            if event.is_final_response() and event.content and event.content.parts:
                texts.extend(p.text for p in event.content.parts if p.text)
        return TargetReply(" ".join(texts).strip() or "(no reply)", tokens)

    async def close(self) -> None:
        runner, toolset = self._runner, self._toolset
        self._runner = self._toolset = None
        try:
            if runner is not None:
                await runner.close()
        finally:
            if toolset is not None:  # always stop the proxy subprocess
                await toolset.close()
