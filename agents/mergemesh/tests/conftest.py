"""Pytest configuration and shared fixtures for MergeMesh test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def fixtures_root() -> Path:
    return PROJECT_ROOT / "fixtures" / "scenarios"
