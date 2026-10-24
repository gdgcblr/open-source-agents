"""Configuration management for AgentRelay."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """AgentRelay runtime configuration."""

    offline_mode: bool = True
    model_provider: str = "offline"  # "offline", "gemini", "mock"
    model_name: str = "gemini-2.5-flash"
    temperature: float = 0.0
    max_tokens: int = 2048
    request_timeout_seconds: int = 15
    max_retries: int = 2
    redact_secrets: bool = True
    gemini_api_key: Optional[str] = field(default=None, repr=False)
    openai_api_key: Optional[str] = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> Config:
        """Create configuration from environment variables."""
        offline_env = os.environ.get("AGENTRELAY_OFFLINE_MODE", "true").lower()
        offline_mode = offline_env in ("1", "true", "yes", "on")

        gemini_key = os.environ.get("GEMINI_API_KEY")
        openai_key = os.environ.get("OPENAI_API_KEY")

        provider = os.environ.get("AGENTRELAY_MODEL_PROVIDER", "offline").lower()

        # If offline_mode is not explicitly set to false, default to offline
        if offline_mode:
            provider = "offline"
        elif provider == "gemini" and not gemini_key:
            # Fall back safely to offline if API key missing
            offline_mode = True
            provider = "offline"

        try:
            temperature = float(os.environ.get("AGENTRELAY_TEMPERATURE", "0.0"))
        except ValueError:
            temperature = 0.0

        try:
            max_tokens = int(os.environ.get("AGENTRELAY_MAX_TOKENS", "2048"))
        except ValueError:
            max_tokens = 2048

        try:
            timeout = int(os.environ.get("AGENTRELAY_REQUEST_TIMEOUT", "15"))
        except ValueError:
            timeout = 15

        try:
            retries = int(os.environ.get("AGENTRELAY_MAX_RETRIES", "2"))
        except ValueError:
            retries = 2

        redact_env = os.environ.get("AGENTRELAY_REDACT_SECRETS", "true").lower()
        redact = redact_env in ("1", "true", "yes", "on")

        return cls(
            offline_mode=offline_mode,
            model_provider=provider,
            model_name=os.environ.get("AGENTRELAY_MODEL_NAME", "gemini-2.5-flash"),
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout_seconds=timeout,
            max_retries=retries,
            redact_secrets=redact,
            gemini_api_key=gemini_key,
            openai_api_key=openai_key,
        )


_default_config: Optional[Config] = None


def get_config() -> Config:
    """Retrieve global configuration or initialize from environment."""
    global _default_config
    if _default_config is None:
        _default_config = Config.from_env()
    return _default_config


def set_config(config: Config) -> None:
    """Override global configuration for testing."""
    global _default_config
    _default_config = config
