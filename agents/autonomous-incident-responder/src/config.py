"""Configuration settings and environment variable management."""

import os
from dataclasses import dataclass, field
from typing import Set
from dotenv import load_dotenv

# Load local environment variables from .env file without overriding existing process env
load_dotenv()


@dataclass
class AgentConfig:
    """Agent runtime configuration and safety boundaries."""

    # Gemini configuration
    api_key: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
    )
    model_name: str = field(
        default_factory=lambda: os.getenv("MODEL_NAME", "gemini-2.5-flash")
    )

    # Execution limits
    max_iterations: int = 10
    max_tool_calls: int = 15
    max_repeated_action_failures: int = 2
    operation_timeout_seconds: float = 35.0

    # Remediation safety allowlist
    permitted_remediations: Set[str] = field(
        default_factory=lambda: {"restart_service", "rollback_config"}
    )

    # Actions classified as high-risk requiring explicit human/policy approval
    high_risk_actions: Set[str] = field(
        default_factory=lambda: {"rollback_config"}
    )

    def has_valid_api_key(self) -> bool:
        return bool(self.api_key and self.api_key != "your_gemini_api_key_here")
