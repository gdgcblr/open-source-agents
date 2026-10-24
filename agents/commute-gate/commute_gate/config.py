from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    ollama_host: str
    ollama_model: str
    route_provider: str
    hf_dataset: str
    policy_file: str
    log_level: str


def load_settings() -> Settings:
    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", "ollama").strip().lower(),
        ollama_host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "phi3:mini").strip(),
        route_provider=os.getenv("ROUTE_PROVIDER", "bengaluru").strip().lower(),
        hf_dataset=os.getenv("HF_DATASET", "").strip(),
        policy_file=os.getenv("POLICY_FILE", str(ROOT / "policy.yaml")).strip(),
        log_level=os.getenv("LOG_LEVEL", "info").strip().lower(),
    )
