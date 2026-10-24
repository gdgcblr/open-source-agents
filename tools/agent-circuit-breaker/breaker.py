"""Loop and budget circuit breaker for agent tool calls.

One CircuitBreaker instance is one agent session; instances share no state.
Usage: call check() before running a tool, run it only if the decision is
allowed, then report the outcome with record_result().
"""

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    allowed: bool
    code: str  # "ok", "repeat", "cycle", "errors" or "budget"
    reason: str


def canonical(tool, args):
    """Stable signature: same tool + same args (any key order) -> same string."""
    return tool + ":" + json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)


class CircuitBreaker:
    def __init__(self, max_repeats=3, max_errors=3, max_calls=20, max_cycle_len=4):
        self.max_repeats = max_repeats  # block the Nth identical call
        self.max_errors = max_errors  # block after N errors in a row
        self.max_calls = max_calls  # total allowed calls per session
        self.max_cycle_len = max_cycle_len  # longest cycle period looked for
        self.history = []  # signatures of allowed calls
        self.consecutive_errors = 0

    def check(self, tool, args=None):
        sig = canonical(tool, args or {})
        if len(self.history) >= self.max_calls:
            return Decision(False, "budget", f"call budget of {self.max_calls} exhausted")
        if self.consecutive_errors >= self.max_errors:
            return Decision(False, "errors", f"{self.consecutive_errors} consecutive tool errors")
        if self.history.count(sig) + 1 >= self.max_repeats:
            return Decision(False, "repeat", f"identical call to '{tool}' would be repeat #{self.max_repeats}")
        period = self._cycle_period(self.history + [sig])
        if period:
            return Decision(False, "cycle", f"repeating cycle of {period} calls detected")
        self.history.append(sig)
        return Decision(True, "ok", "allowed")

    def record_result(self, ok):
        self.consecutive_errors = 0 if ok else self.consecutive_errors + 1

    def _cycle_period(self, seq):
        # A cycle is the last p calls equal to the p calls before them (A B A B).
        # Period 1 is a plain repeat, which max_repeats already handles.
        for p in range(2, self.max_cycle_len + 1):
            if len(seq) >= 2 * p and seq[-p:] == seq[-2 * p:-p] and len(set(seq[-p:])) > 1:
                return p
        return 0
