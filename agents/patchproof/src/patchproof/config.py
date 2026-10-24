"""Configuration and resource bounds for PatchProof runs."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        val = int(raw.strip())
        return val if val > 0 else default
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class PatchProofConfig(BaseModel):
    """Runtime bounds and policy configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: str = Field(default="deterministic")
    model_provider: str = Field(default="none")
    model_name: str = Field(default="")
    enable_sandbox: bool = Field(default=False)
    sandbox_image: str = Field(default="")
    max_diff_bytes: int = Field(default=307_200, ge=1024)
    max_source_files: int = Field(default=30, ge=1)
    max_file_bytes: int = Field(default=81_920, ge=512)
    max_total_context_bytes: int = Field(default=512_000, ge=4096)
    max_comments: int = Field(default=100, ge=1)
    max_agent_parallelism: int = Field(default=4, ge=1, le=16)
    max_model_calls: int = Field(default=20, ge=0)
    max_retries_per_agent: int = Field(default=1, ge=0, le=3)
    max_verification_loops: int = Field(default=1, ge=0, le=2)
    max_check_seconds: int = Field(default=120, ge=1)
    max_run_seconds: int = Field(default=300, ge=1)
    max_excerpt_bytes: int = Field(default=4_096, ge=128)
    max_captured_output_bytes: int = Field(default=102_400, ge=512)
    fixtures_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "fixtures"
    )

    @classmethod
    def from_env(cls, fixtures_dir: Path | None = None) -> PatchProofConfig:
        """Load configuration from environment variables with safe defaults."""
        kwargs: dict[str, object] = {
            "mode": os.environ.get("PATCHPROOF_MODE", "deterministic") or "deterministic",
            "model_provider": os.environ.get("PATCHPROOF_MODEL_PROVIDER", "none") or "none",
            "model_name": os.environ.get("PATCHPROOF_MODEL_NAME", "") or "",
            "enable_sandbox": _env_bool("PATCHPROOF_ENABLE_SANDBOX", False),
            "sandbox_image": os.environ.get("PATCHPROOF_SANDBOX_IMAGE", "") or "",
            "max_diff_bytes": _env_int("PATCHPROOF_MAX_DIFF_BYTES", 307_200),
            "max_source_files": _env_int("PATCHPROOF_MAX_SOURCE_FILES", 30),
            "max_file_bytes": _env_int("PATCHPROOF_MAX_FILE_BYTES", 81_920),
            "max_run_seconds": _env_int("PATCHPROOF_MAX_RUN_SECONDS", 300),
            "max_check_seconds": _env_int("PATCHPROOF_MAX_CHECK_SECONDS", 120),
            "max_model_calls": _env_int("PATCHPROOF_MAX_MODEL_CALLS", 20),
        }
        if fixtures_dir is not None:
            kwargs["fixtures_dir"] = fixtures_dir
        return cls(**kwargs)  # type: ignore[arg-type]

