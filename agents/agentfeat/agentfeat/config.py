"""Configuration management for AgentFeat."""

import os
from pathlib import Path
from typing import Optional


def load_dotenv(dotenv_path: Optional[Path] = None) -> None:
    """Lightweight .env loader without third-party dependencies."""
    if dotenv_path is None:
        dotenv_path = Path.cwd() / ".env"
    if not dotenv_path.is_file():
        return

    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


class Config:
    """AgentFeat runtime configuration."""

    def __init__(self) -> None:
        load_dotenv()
        self.api_key: str = os.getenv("GEMINI_API_KEY", "")
        self.model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self.offline_mode: bool = os.getenv("AGENTFEAT_OFFLINE_MODE", "false").lower() in ("true", "1", "yes")
        self.verbose: bool = os.getenv("AGENTFEAT_VERBOSE", "false").lower() in ("true", "1", "yes")

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("your_"))


config = Config()
