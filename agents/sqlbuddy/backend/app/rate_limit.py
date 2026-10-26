"""Simple process-local sliding window limiter for the local single-instance app."""

import threading
import time
from collections import defaultdict, deque

from fastapi.responses import JSONResponse


class RateLimiter:
    """Limit requests per client address without an additional service."""

    def __init__(self, app, max_requests: int, window_seconds: int):
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def is_limited(self, client: str, now: float | None = None) -> bool:
        """Return whether this client has used its allowance in the time window."""
        now = time.monotonic() if now is None else now
        with self._lock:
            bucket = self._requests[client]
            while bucket and now - bucket[0] >= self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                return True
            bucket.append(now)
            return False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path") == "/api/v1/health":
            await self.app(scope, receive, send)
            return
        client_info = scope.get("client")
        client = client_info[0] if client_info else "unknown"
        if self.is_limited(client):
            response = JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limited", "message": "Too many requests. Wait a little and try again."}},
                headers={"Retry-After": str(self.window_seconds)},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
