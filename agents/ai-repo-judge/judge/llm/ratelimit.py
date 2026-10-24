"""Client-side rate limiting that keeps us inside free-tier quotas (e.g. Groq: 8K tokens/min, 30 req/min)."""

from __future__ import annotations

import re
import threading
import time
from collections import deque

NUMBER = re.compile(r"\d+(?:\.\d+)?")
DURATION = re.compile(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m(?!s))?(?:(\d+(?:\.\d+)?)s)?(?:(\d+(?:\.\d+)?)ms)?$")


def parse_duration(value: str | None) -> float | None:
    """Parse '2m59.56s', '7.66s', '120ms' or plain seconds into seconds."""
    if not value:
        return None
    value = value.strip()
    if NUMBER.fullmatch(value):
        return float(value)
    m = DURATION.match(value)
    if not m or not any(m.groups()):
        return None
    h, mins, s, ms = (float(g) if g else 0.0 for g in m.groups())
    return h * 3600 + mins * 60 + s + ms / 1000


class RateLimiter:
    """Sliding 60-second window over requests and tokens, plus server-reported remaining budget."""

    def __init__(self, tpm: int, rpm: int, sleep=time.sleep, clock=time.monotonic):
        self.tpm, self.rpm = tpm, rpm
        self._events: deque[tuple[float, int]] = deque()
        self._blocked_until = 0.0
        self._sleep, self._clock = sleep, clock
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        while self._events and now - self._events[0][0] >= 60:
            self._events.popleft()

    def wait_time(self, tokens: int) -> float:
        now = self._clock()
        self._prune(now)
        wait = max(0.0, self._blocked_until - now)
        used = sum(t for _, t in self._events)
        if self._events and (used + tokens > self.tpm or len(self._events) >= self.rpm):
            wait = max(wait, 60 - (now - self._events[0][0]) + 0.5)
        return wait

    def acquire(self, tokens: int) -> float:
        """Block until a request of `tokens` fits; returns seconds waited."""
        waited = 0.0
        with self._lock:
            while (w := self.wait_time(min(tokens, self.tpm))) > 0:
                self._sleep(w)
                waited += w
            self._events.append((self._clock(), tokens))
        return waited

    def record(self, actual_tokens: int) -> None:
        """Replace the last estimate with the real usage reported by the API."""
        with self._lock:
            if self._events:
                ts, _ = self._events.pop()
                self._events.append((ts, actual_tokens))

    def update_from_headers(self, headers) -> None:
        remaining = headers.get("x-ratelimit-remaining-tokens")
        reset = parse_duration(headers.get("x-ratelimit-reset-tokens"))
        valid = remaining is not None and reset is not None and NUMBER.fullmatch(str(remaining).strip())
        if valid and float(remaining) < self.tpm * 0.1:
            self._blocked_until = max(self._blocked_until, self._clock() + reset)

    def block_for(self, seconds: float) -> None:
        self._blocked_until = max(self._blocked_until, self._clock() + seconds)
