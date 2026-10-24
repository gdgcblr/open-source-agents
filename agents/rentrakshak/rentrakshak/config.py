from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_PKG_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PKG_ROOT / ".env")


def package_root() -> Path:
    return _PKG_ROOT


def default_db_path() -> Path:
    raw = os.environ.get("RENTRAKSHAK_DB_PATH", str(_PKG_ROOT / "data" / "rentrakshak.db"))
    return Path(raw)


def model_name() -> str:
    return os.environ.get("RENTRAKSHAK_MODEL", "gemini-2.0-flash")


def google_api_key() -> str | None:
    return os.environ.get("GOOGLE_API_KEY") or None
