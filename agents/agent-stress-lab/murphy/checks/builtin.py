"""Built-in checks: trace rules (generic) and state checks (python function, HTTP)."""

from __future__ import annotations

import json
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any, Callable

from murphy.checks.base import CheckResult, RunContext
from murphy.proxy.policy import key_of


def _executed(e: dict) -> bool:
    """The call really happened upstream (including a commit reported to the agent as a timeout)."""
    return e.get("upstream_called", False) and (e.get("ok") or e.get("fault") == "timeout_after_commit")


@dataclass
class TraceCheck:
    id: str
    rule: str  # max_calls_per_key | called | not_called | order
    label: str = "wrong"
    hint: str = ""
    tool: str = "*"
    key: list[str] = field(default_factory=list)
    max: int | None = None
    min: int = 0
    before: str = ""
    after: str = ""

    def run(self, ctx: RunContext) -> CheckResult:
        events = [e for e in ctx.tool_events if _executed(e)]
        ok, msg = getattr(self, f"_{self.rule}")(events)
        return CheckResult(self.id, ok, self.label, msg, "" if ok else self.hint)

    def _matching(self, events):
        return [e for e in events if fnmatch(e["tool"], self.tool)]

    def _max_calls_per_key(self, events):
        counts = Counter(key_of(e["args"], self.key) for e in self._matching(events))
        worst = max(counts.values(), default=0)
        limit = 1 if self.max is None else self.max
        over = {"/".join(k): n for k, n in counts.items() if n > limit}
        return worst <= limit, (f"{self.tool} executed {over} times per key (max {limit})" if over
                                else f"{self.tool} ≤ {limit} per key")

    def _called(self, events):
        n = len(self._matching(events))
        ok = n >= self.min and (self.max is None or n <= self.max)
        return ok, f"{self.tool} executed {n} times (expected {self.min}..{self.max if self.max is not None else '∞'})"

    def _not_called(self, events):
        n = len(self._matching(events))
        return n == 0, f"{self.tool} executed {n} times (expected none)"

    def _order(self, events):
        names = [e["tool"] for e in events]
        b = next((i for i, n in enumerate(names) if fnmatch(n, self.before)), None)
        a = next((i for i, n in enumerate(names) if fnmatch(n, self.after)), None)
        if a is None:
            return True, f"{self.after} not executed"
        return b is not None and b < a, f"{self.before} {'precedes' if b is not None and b < a else 'does not precede'} {self.after}"


@dataclass
class PythonCheck:
    id: str
    fn: Callable[[RunContext], Any]
    label: str = "wrong"
    hint: str = ""

    def run(self, ctx: RunContext) -> CheckResult:
        out = self.fn(ctx)
        if isinstance(out, CheckResult):
            return out
        ok = bool(out)
        return CheckResult(self.id, ok, self.label, f"{getattr(self.fn, '__name__', 'fn')} returned {ok}", "" if ok else self.hint)


@dataclass
class HttpCheck:
    id: str
    url: str
    path: str
    equals: Any
    label: str = "wrong"
    hint: str = ""
    timeout_s: float = 10

    def run(self, ctx: RunContext) -> CheckResult:
        url = ctx.substitute(self.url)
        try:
            with urllib.request.urlopen(url, timeout=self.timeout_s) as resp:
                value: Any = json.load(resp)
            for part in self.path.split("."):
                value = value[int(part)] if isinstance(value, list) else value[part]
        except Exception as exc:
            return CheckResult(self.id, False, self.label, f"GET {url} failed: {exc}", self.hint)
        ok = value == self.equals
        return CheckResult(self.id, ok, self.label, f"{self.path} = {value!r} (expected {self.equals!r})", "" if ok else self.hint)
