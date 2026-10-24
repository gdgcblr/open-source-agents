"""Small file helpers shared by the checks."""

from __future__ import annotations

import re
from pathlib import Path

TEST_FILE = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)(test_[^/]*|[^/]*_test\.\w+|[^/]*\.(test|spec)\.\w+|conftest\.py)$")


def is_test_file(rel: str) -> bool:
    """tests/, test_x.py, x_test.go, x.test.js. Not latest_runner.py or contest.py."""
    return bool(TEST_FILE.search(rel))


def read(path: Path, limit: int = 2_000_000) -> str:
    """File contents as text; undecodable bytes are replaced, never a reason to skip."""
    with open(path, "rb") as fh:
        return fh.read(limit).decode("utf-8", "replace")
