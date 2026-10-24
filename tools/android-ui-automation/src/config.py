"""Configuration loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional


def _parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be a number, got {raw!r}") from exc
    if value < 0:
        raise ValueError(f"{key} must be >= 0, got {value}")
    return value


@dataclass(frozen=True)
class Config:
    adb_path: str = "adb"
    device_id: Optional[str] = None
    command_timeout: float = 30.0
    ui_wait_timeout: float = 5.0

    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> "Config":
        """Build a config. Real environment variables win over ``.env`` values."""
        merged: Dict[str, str] = {}
        candidates = (
            [Path(env_file)]
            if env_file
            else [Path(__file__).resolve().parent.parent / ".env", Path.cwd() / ".env"]
        )
        for candidate in candidates:
            merged.update(_parse_env_file(candidate))
        merged.update({k: v for k, v in os.environ.items()})

        return cls(
            adb_path=merged.get("ADB_PATH", "").strip() or "adb",
            device_id=merged.get("ANDROID_DEVICE_ID", "").strip() or None,
            command_timeout=_float(merged, "COMMAND_TIMEOUT_SECONDS", 30.0),
            ui_wait_timeout=_float(merged, "UI_WAIT_TIMEOUT_SECONDS", 5.0),
        )
