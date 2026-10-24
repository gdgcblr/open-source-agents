"""Configuration module for DevOps Migration Agent.

Handles configuration loading from environment variables, CLI parameters,
and sensible defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentConfig:
    """Agent runtime configuration."""

    # Model and Google AI / ADK configuration
    model_name: str = field(default_factory=lambda: os.getenv("MODEL_NAME", "gemini-2.5-flash"))
    google_api_key: str | None = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY"))
    google_genai_use_vertexai: bool = field(
        default_factory=lambda: (
            os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "false").lower() in ("true", "1", "yes")
        )
    )
    google_cloud_project: str | None = field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT")
    )
    google_cloud_location: str = field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    )

    # Runtime behavior
    offline_mode: bool = field(
        default_factory=lambda: os.getenv("OFFLINE_MODE", "false").lower() in ("true", "1", "yes")
    )
    verbose: bool = field(
        default_factory=lambda: os.getenv("VERBOSE", "false").lower() in ("true", "1", "yes")
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())

    # Paths and defaults
    default_output_dir: Path = field(
        default_factory=lambda: Path(os.getenv("MIGRATION_OUTPUT_DIR", "./migration-output"))
    )
    service_connection_name: str = field(
        default_factory=lambda: os.getenv("AZURE_SERVICE_CONNECTION", "azure-service-connection")
    )
    default_vm_image: str = field(
        default_factory=lambda: os.getenv("DEFAULT_VM_IMAGE", "ubuntu-latest")
    )

    def is_offline(self) -> bool:
        """Determines if the agent should operate in offline mode."""
        if self.offline_mode:
            return True
        if not self.google_api_key and not self.google_genai_use_vertexai:
            return True
        return False


def get_config(**overrides: object) -> AgentConfig:
    """Instantiate configuration with optional keyword overrides."""
    cfg = AgentConfig()
    for key, value in overrides.items():
        if hasattr(cfg, key) and value is not None:
            setattr(cfg, key, value)
    return cfg
