"""Pytest configuration and shared fixtures for DevGuard."""

import pytest
import yaml
from pathlib import Path


@pytest.fixture
def sample_config_dict():
    """Returns a valid configuration dictionary."""
    return {
        "default_policy": "ask",
        "allow": [
            ["git", "status"],
            ["git", "diff"],
            ["git", "log"],
            ["python3", "-m", "pytest"],
            ["echo"],
        ],
        "ask": [
            ["git", "commit"],
            ["git", "push"],
        ],
        "deny": [
            ["git", "reset", "--hard"],
            ["git", "clean", "-fdx"],
        ],
    }


@pytest.fixture
def sample_config_file(tmp_path: Path, sample_config_dict: dict) -> Path:
    """Writes a sample YAML config to a temporary file."""
    config_file = tmp_path / "devguard.yaml"
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(sample_config_dict, f)
    return config_file

