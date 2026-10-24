"""Environment and runtime configuration for adk-leak-arena."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class ArenaConfig:
    """Runtime configuration for the ADK Leak Arena server and evaluator."""

    app_name: str = field(
        default_factory=lambda: os.environ.get("ARENA_APP_NAME", "acme_enterprise_copilot")
    )
    db_dsn: str = field(
        default_factory=lambda: os.environ.get(
            "ARENA_DB_DSN",
            os.environ.get(
                "MEMSHIELD_DB_DSN",
                "postgresql://memshield_app:memshield_pass@localhost:54330/memshield",
            ),
        )
    )
    admin_dsn: str = field(
        default_factory=lambda: os.environ.get(
            "ARENA_ADMIN_DSN",
            "postgresql://postgres:postgres_admin_pass@localhost:54330/memshield",
        )
    )
    ollama_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "OLLAMA_BASE_URL", "http://host.docker.internal:11434"
        )
    )
    ollama_model: str = field(
        default_factory=lambda: os.environ.get("OLLAMA_MODEL", "ollama_chat/gemma3:4b")
    )
    gemini_api_key: str = field(
        default_factory=lambda: os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY", "")
    )
    gemini_model: str = field(
        default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    )
    # Run one deterministic reference benchmark at server startup so Run History is populated.
    startup_baseline: bool = field(
        default_factory=lambda: os.environ.get("ARENA_STARTUP_BASELINE", "1").lower()
        not in ("0", "false", "no")
    )
    top_k: int = 3
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
