import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def sandbox_root(tmp_path, monkeypatch):
    """Confine the tools to each test's temp dir, like ALLOWED_ROOT does in real use."""
    monkeypatch.setenv("ALLOWED_ROOT", str(tmp_path))
    monkeypatch.delenv("BASE_REF", raising=False)
    return tmp_path
