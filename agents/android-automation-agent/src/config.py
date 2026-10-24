"""Runtime settings for the agent, read from environment variables.

A ``.env`` file in the project root (``agents/android-automation-agent/.env``)
is loaded into the process environment without overriding variables that are
already set, so Google/ADK credentials placed there are picked up too.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AUTOMATION_PATH = PROJECT_ROOT.parent.parent / "tools" / "android-ui-automation"


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


def load_env_file(path: Optional[Path] = None) -> None:
    """Copy non-empty values from ``.env`` into ``os.environ`` (never overriding)."""
    for key, value in _parse_env_file(path or PROJECT_ROOT / ".env").items():
        if value and key not in os.environ:
            os.environ[key] = value


def _number(env: Mapping[str, str], key: str, default: float, minimum: float = 0.0) -> float:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be a number, got {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{key} must be >= {minimum}, got {value}")
    return value


def _flag(env: Mapping[str, str], key: str, default: bool = False) -> bool:
    raw = env.get(key, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    model: str = "gemini-flash-latest"
    max_retries: int = 2
    max_tool_calls: int = 40
    log_level: str = "INFO"
    log_typed_text: bool = False
    adb_path: str = "adb"
    device_id: Optional[str] = None
    command_timeout: float = 30.0
    ui_wait_timeout: float = 5.0
    automation_path: Path = DEFAULT_AUTOMATION_PATH

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Settings":
        e = os.environ if env is None else env
        automation_path = e.get("ANDROID_AUTOMATION_PATH", "").strip()
        return cls(
            model=e.get("AGENT_MODEL", "").strip() or cls.model,
            max_retries=int(_number(e, "AGENT_MAX_RETRIES", 2)),
            max_tool_calls=int(_number(e, "AGENT_MAX_TOOL_CALLS", 40, minimum=1)),
            log_level=(e.get("AGENT_LOG_LEVEL", "").strip() or "INFO").upper(),
            log_typed_text=_flag(e, "AGENT_LOG_TYPED_TEXT", False),
            adb_path=e.get("ADB_PATH", "").strip() or "adb",
            device_id=e.get("ANDROID_DEVICE_ID", "").strip() or None,
            command_timeout=_number(e, "COMMAND_TIMEOUT_SECONDS", 30.0),
            ui_wait_timeout=_number(e, "UI_WAIT_TIMEOUT_SECONDS", 5.0),
            automation_path=(
                Path(automation_path).expanduser() if automation_path else DEFAULT_AUTOMATION_PATH
            ),
        )


_SETTINGS: Optional[Settings] = None


def get_settings(reload: bool = False) -> Settings:
    """Load ``.env`` once and return the cached settings."""
    global _SETTINGS
    if _SETTINGS is None or reload:
        load_env_file()
        _SETTINGS = Settings.from_env()
    return _SETTINGS
