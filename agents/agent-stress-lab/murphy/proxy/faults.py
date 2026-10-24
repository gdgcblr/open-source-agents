"""Fault selection: which call to which tool gets which fault."""

from __future__ import annotations

import random
from fnmatch import fnmatch

from murphy.config.schema import FaultSpec


class FaultEngine:
    def __init__(self, specs: list[FaultSpec], seed: int = 0) -> None:
        self.specs = specs
        self.rng = random.Random(seed)

    def pick(self, tool: str, call_index: int) -> FaultSpec | None:
        """call_index: 1-based count of calls to `tool` in this run. First matching spec wins."""
        for spec in self.specs:
            if not fnmatch(tool, spec.tool):
                continue
            if spec.rate is not None:
                if self.rng.random() < spec.rate:
                    return spec
            elif spec.on_call == call_index:
                return spec
        return None
