"""Configuration settings for PII Redaction Agent."""
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # AI Model Configuration (Ollama - local, privacy-preserving)
    OLLAMA_URL: str = "http://localhost:11434/api/generate"
    OLLAMA_MODEL: str = "llama3.2"

    # Detection Configuration
    CONFIDENCE_THRESHOLD: float = 0.7
    ENABLE_REGEX_DETECTION: bool = True
    ENABLE_AI_DETECTION: bool = False

    # Redaction Configuration
    REDACTION_STRATEGY: Literal["full", "partial", "hash"] = "full"
    REDACTION_CHAR: str = "[REDACTED]"
    PARTIAL_REDACTION_LENGTH: int = 4

    # Compliance Modes
    COMPLIANCE_MODE: Literal["GDPR", "CCPA", "HIPAA", "STRICT"] = "GDPR"

    # Guardrails
    MAX_INPUT_SIZE: int = 10_000_000  # 10MB
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_PERIOD: int = 60  # seconds
    ENABLE_AUDIT_LOGGING: bool = True
    AUDIT_LOG_PATH: str = "audit.log"

    # Evaluation
    ENABLE_EVALUATION: bool = False
    EVALUATION_DATA_PATH: str = "test_data/"

    # Logging
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
