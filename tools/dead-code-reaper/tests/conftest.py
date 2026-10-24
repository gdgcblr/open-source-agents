import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def make_project(tmp_path):
    """Write {relative path: source} into a fresh project directory."""
    count = [0]

    def make(files: dict[str, str]) -> Path:
        count[0] += 1
        root = tmp_path / ("proj" if count[0] == 1 else f"proj{count[0]}")
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
        return root
    return make
