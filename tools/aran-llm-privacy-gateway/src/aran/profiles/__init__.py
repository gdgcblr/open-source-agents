"""Profiles map each PII type to an action: mask (reversible token), age_band (generalise) or keep."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

_DIR = Path(__file__).parent
ACTIONS = {"mask", "age_band", "keep"}


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    actions: dict[str, str]

    def action_for(self, pii_type: str) -> str:
        # Unknown types are masked: fail closed, never open.
        return self.actions.get(pii_type, "mask")


def available() -> list[str]:
    return sorted(p.stem for p in _DIR.glob("*.yaml"))


def load(name: str) -> Profile:
    path = _DIR / f"{name}.yaml"
    if not path.is_file():
        raise ValueError(f"Unknown profile {name!r}. Available: {', '.join(available())}")
    data = yaml.safe_load(path.read_text())
    bad = {k: v for k, v in data["actions"].items() if v not in ACTIONS}
    if bad:
        raise ValueError(f"Profile {name!r} has invalid actions: {bad}")
    return Profile(data["name"], data.get("description", ""), data["actions"])
