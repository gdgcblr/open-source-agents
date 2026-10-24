"""Environment configuration; no provider imports or secret-bearing errors."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def advisory_path() -> Path:
    return Path(os.getenv("TRIAGE_ADVISORY_PATH", str(PROJECT_ROOT / "data/advisories.json")))


def log_root() -> Path:
    return Path(os.getenv("TRIAGE_LOG_DIR", str(PROJECT_ROOT / "samples"))).expanduser().resolve()


def bounded_int(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        if not 1 <= value <= maximum:
            raise ValueError
        return value
    except ValueError:
        raise ValueError(f"Invalid {name}; use an integer from 1 to {maximum}") from None
