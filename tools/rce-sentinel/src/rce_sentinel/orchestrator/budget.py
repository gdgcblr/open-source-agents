"""Per-run budget governor: tokens, dollars, LLM seconds, and an optional wall deadline."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class Budget:
    max_tokens: int
    max_usd: float
    max_llm_seconds: float
    deadline: float | None = None  # time.monotonic() value
    tokens: int = 0
    usd: float = 0.0
    llm_seconds: float = 0.0
    exhausted: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def from_policy(cls, policy: dict, wall_seconds: float | None = None) -> Budget:
        b = policy.get("budget", {})
        deadline = time.monotonic() + wall_seconds if wall_seconds else None
        return cls(max_tokens=int(b.get("max_tokens", 200_000)),
                   max_usd=float(b.get("max_usd", 0.05)),
                   max_llm_seconds=float(b.get("max_llm_seconds", 60)),
                   deadline=deadline)

    def remaining_seconds(self) -> float:
        left = self.max_llm_seconds - self.llm_seconds
        if self.deadline is not None:
            left = min(left, self.deadline - time.monotonic())
        return left

    def allow(self, est_tokens: int, est_usd: float) -> bool:
        with self._lock:
            if self.exhausted:
                return False
            if self.tokens + est_tokens > self.max_tokens:
                self.exhausted = f"token cap {self.max_tokens} reached"
            elif self.usd + est_usd > self.max_usd:
                self.exhausted = f"dollar cap ${self.max_usd:.2f} reached"
            elif self.remaining_seconds() <= 0.5:
                self.exhausted = "time budget reached"
            return self.exhausted is None

    def charge(self, tokens: int, usd: float, seconds: float) -> None:
        with self._lock:
            self.tokens += tokens
            self.usd += usd
            self.llm_seconds += seconds
