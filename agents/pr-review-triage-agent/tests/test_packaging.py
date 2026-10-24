from __future__ import annotations

import tomllib
from pathlib import Path


def test_project_metadata_supports_python_3_10_and_cli_entry_point():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    assert data["project"]["requires-python"] == ">=3.10"
    assert "agent-reality-check" in data["project"].get("scripts", {})
