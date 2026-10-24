"""HTTP chat-endpoint adapter for agents running as a service (any framework or language).

Contract: POST <url> {"session_id": str, "message": str} -> {"reply": str, "tokens"?: int}.
Tool calls are only observed if the service routes its MCP tools through the murphy proxy;
otherwise the run is judged on conversation and state checks only.
"""

from __future__ import annotations

import asyncio
import json
import urllib.request
import uuid

from murphy.targets.base import TargetReply, ToolEndpoint


class HttpTarget:
    def __init__(self, url: str, label: str | None = None, timeout_s: float = 120, headers: dict | None = None) -> None:
        self.url = url
        self.label = label or url
        self.timeout_s = timeout_s
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.session_id = ""

    async def start(self, tools: ToolEndpoint | None) -> None:
        self.session_id = uuid.uuid4().hex

    def _post(self, message: str) -> dict:
        body = json.dumps({"session_id": self.session_id, "message": message}).encode()
        req = urllib.request.Request(self.url, data=body, headers=self.headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            return json.load(resp)

    async def send(self, message: str) -> TargetReply:
        data = await asyncio.to_thread(self._post, message)
        return TargetReply(str(data.get("reply", "")), int(data.get("tokens", 0) or 0))

    async def close(self) -> None:
        pass
