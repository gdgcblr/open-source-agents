"""Compare the results of the same calls against the old and new server."""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass

from .runner import NOT_EXECUTED, CallRecord


@dataclass(frozen=True)
class Difference:
    id: str
    tool: str
    old: CallRecord
    new: CallRecord
    diff_lines: tuple[str, ...]


def _canonical(record: CallRecord) -> list[str]:
    return json.dumps(record.comparable(), indent=2, sort_keys=True, ensure_ascii=True).splitlines()


def compare(old: list[CallRecord], new: list[CallRecord]) -> list[Difference]:
    differences: list[Difference] = []
    for a, b in zip(old, new, strict=True):
        if a.id != b.id:
            raise ValueError("record lists are not aligned")
        if a.comparable() == b.comparable():
            continue
        lines = tuple(difflib.unified_diff(_canonical(a), _canonical(b), "old", "new", lineterm="", n=2))
        differences.append(Difference(a.id, a.tool, a, b, lines))
    return differences


def incomplete(old: list[CallRecord], new: list[CallRecord]) -> list[str]:
    """IDs of calls that were deliberately not executed on at least one side."""
    return [a.id for a, b in zip(old, new, strict=True) if a.status in NOT_EXECUTED or b.status in NOT_EXECUTED]
