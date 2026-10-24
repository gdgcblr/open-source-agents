from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()
