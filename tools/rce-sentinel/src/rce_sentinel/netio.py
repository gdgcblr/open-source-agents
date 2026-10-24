"""Outbound HTTP restricted to allowlisted hosts. URLs from fetched text or model output are
never passed here; collectors only use URLs from config."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import httpx


class BlockedHost(Exception):
    pass


class SafeClient:
    def __init__(self, allowed_hosts: list[str], timeout: float = 15.0,
                 max_bytes: int = 5_000_000, user_agent: str = "rce-sentinel/0.1"):
        self.allowed = {h.lower() for h in allowed_hosts}
        self.max_bytes = max_bytes
        self.offline = os.environ.get("RCE_SENTINEL_OFFLINE", "").lower() in {"1", "true", "on"}
        self._client = httpx.Client(timeout=timeout, follow_redirects=False,
                                    headers={"User-Agent": user_agent})

    def check(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in self.allowed:
            raise BlockedHost(f"host not allowlisted: {parsed.hostname}")

    def request(self, method: str, url: str, **kw: Any) -> httpx.Response:
        if self.offline:
            raise httpx.ConnectError("offline mode")
        self.check(url)
        with self._client.stream(method, url, **kw) as resp:
            body = b""
            for chunk in resp.iter_bytes():
                body += chunk
                if len(body) > self.max_bytes:
                    raise ValueError(f"response over {self.max_bytes} bytes: {url}")
            return httpx.Response(resp.status_code, headers=resp.headers, content=body,
                                  request=resp.request)

    def get_json(self, url: str, **kw: Any) -> Any:
        resp = self.request("GET", url, **kw)
        resp.raise_for_status()
        return resp.json()

    def post_json(self, url: str, payload: Any, **kw: Any) -> Any:
        resp = self.request("POST", url, json=payload, **kw)
        resp.raise_for_status()
        return resp.json() if resp.content else None
