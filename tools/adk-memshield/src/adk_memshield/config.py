"""Configuration models for adk-memshield."""

from __future__ import annotations

import os
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class MemShieldConfig(BaseModel):
    """Configuration for MemShieldMemoryService.

    Attributes:
        dsn: PostgreSQL connection URI using a non-superuser role (e.g. memshield_app)
            so PostgreSQL Row-Level Security (RLS) policies are strictly enforced.
        tenant_id: Active tenant identifier bound to transaction-local context
            (`app.current_tenant_id`).
        agent_clearance: Clearance level (1..5) of the active agent/caller bound to
            transaction-local context (`app.agent_clearance`).
        default_scope: Default visibility scope for newly stored memories
            (`'private'` or `'tenant_shared'`).
        default_min_clearance: Default minimum clearance level (1..5) required to
            read `'tenant_shared'` memories.
        top_k: Maximum number of memories returned by `search_memory`.
        min_similarity: Optional minimum cosine similarity threshold for retrieval.
        embedding_model: FastEmbed ONNX model identifier.
        embedding_dim: Expected embedding vector dimensionality.
        table_name: Target PostgreSQL table name (`'memories'` by default).
        simulate_missing_app_filter: Chaos/testing flag. When True, omits application-layer
            SQL `WHERE` clauses during `search_memory` to verify that PostgreSQL RLS
            independently prevents cross-tenant and cross-user leakage.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    dsn: str = Field(
        default_factory=lambda: os.environ.get(
            "MEMSHIELD_DB_DSN",
            "postgresql://memshield_app:memshield_pass@localhost:54329/memshield",
        )
    )
    tenant_id: str = Field(default="default", min_length=1)
    agent_clearance: int = Field(default=1, ge=1, le=5)
    default_scope: Literal["private", "tenant_shared"] = Field(default="private")
    default_min_clearance: int = Field(default=1, ge=1, le=5)
    top_k: int = Field(default=5, ge=1, le=100)
    min_similarity: float | None = Field(default=None, ge=-1.0, le=1.0)
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5")
    embedding_dim: int = Field(default=384, ge=1)
    table_name: str = Field(default="memories")
    simulate_missing_app_filter: bool = Field(default=False)

    @field_validator("table_name")
    @classmethod
    def _validate_table_name(cls, value: str) -> str:
        if not _SAFE_IDENTIFIER_RE.match(value):
            raise ValueError(f"Unsafe SQL table identifier: {value!r}")
        return value
