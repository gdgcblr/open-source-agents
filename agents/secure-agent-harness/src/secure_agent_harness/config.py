"""Typed configuration with safe, bounded defaults."""
from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    value = default if raw is None or raw == "" else int(raw)
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    value = default if raw is None or raw == "" else float(raw)
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    max_steps: int
    max_tool_calls: int
    max_input_chars: int
    max_output_tokens: int
    max_estimated_cost_usd: float
    input_usd_per_million_tokens: float
    output_usd_per_million_tokens: float
    memory_db_path: Path
    user_id: str
    audit_log_path: Path

    @classmethod
    def from_env(cls) -> "Settings":
        user_id = os.getenv("AGENT_USER_ID", "local-user").strip()
        if not user_id or len(user_id) > 128:
            raise ValueError("AGENT_USER_ID must be 1-128 characters")
        return cls(
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip(),
            max_steps=_int_env("MAX_STEPS", 6, 1, 20),
            max_tool_calls=_int_env("MAX_TOOL_CALLS", 4, 0, 20),
            max_input_chars=_int_env("MAX_INPUT_CHARS", 8000, 100, 50000),
            max_output_tokens=_int_env("MAX_OUTPUT_TOKENS", 700, 32, 4000),
            max_estimated_cost_usd=_float_env("MAX_ESTIMATED_COST_USD", 0.03, 0.0001, 100),
            input_usd_per_million_tokens=_float_env(
                "INPUT_USD_PER_MILLION_TOKENS", 0.40, 0, 10000
            ),
            output_usd_per_million_tokens=_float_env(
                "OUTPUT_USD_PER_MILLION_TOKENS", 1.60, 0, 10000
            ),
            memory_db_path=Path(os.getenv("MEMORY_DB_PATH", ".data/memory.sqlite3")),
            user_id=user_id,
            audit_log_path=Path(os.getenv("AUDIT_LOG_PATH", ".data/audit.jsonl")),
        )
