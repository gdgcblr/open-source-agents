"""Shared pytest fixtures.

Ensures the project root is importable and exposes the fixtures
directory so tests never touch real git or the network.
"""

import os
import sys

import pytest

# Make the project root importable when pytest is run from elsewhere.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


@pytest.fixture
def fixtures_dir() -> str:
    """Absolute path to tests/fixtures."""
    return _FIXTURES


@pytest.fixture
def read_fixture():
    """Return a function that reads a fixture's text by file name."""

    def _read(name: str) -> str:
        with open(os.path.join(_FIXTURES, name), "r", encoding="utf-8") as handle:
            return handle.read()

    return _read
