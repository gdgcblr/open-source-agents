"""Utilities for loading and formatting synthetic PR diffs."""

from __future__ import annotations

from pathlib import Path

from domain.models import DiffFileRef


def load_scenario_diffs(scenario_root: Path, diff_refs: list[DiffFileRef]) -> list[DiffFileRef]:
    """Load diff text contents safely from the scenario fixture directory."""
    loaded: list[DiffFileRef] = []
    root_resolved = scenario_root.resolve()

    for ref in diff_refs:
        candidate = (scenario_root / ref.path).resolve()
        if not str(candidate).startswith(str(root_resolved)):
            raise ValueError(f"Diff path escapes scenario fixture root: {ref.path}")
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError(f"Diff fixture file not found: {candidate}")

        content = candidate.read_text(encoding="utf-8")
        loaded.append(
            DiffFileRef(
                repo=ref.repo,
                path=ref.path,
                summary=ref.summary,
                content=content,
            )
        )
    return loaded
