"""Evidence hashing and summary helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path


def compute_file_sha256(file_path: Path) -> str:
    """Compute a short SHA-256 hex digest for a fixture file."""
    if not file_path.exists() or not file_path.is_file():
        return "missing"
    digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
    return digest[:16]


def compute_scenario_hashes(scenario_root: Path, relative_paths: list[str]) -> dict[str, str]:
    """Compute deterministic hashes for all scenario input files."""
    hashes: dict[str, str] = {}
    for rel in relative_paths:
        if not rel:
            continue
        target = (scenario_root / rel).resolve()
        hashes[rel] = compute_file_sha256(target)
    return hashes
