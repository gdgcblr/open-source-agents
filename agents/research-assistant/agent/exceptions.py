"""Enterprise exception hierarchy for Research Assistant."""


class ResearchAssistantError(Exception):
    """Base exception for all research assistant errors."""
    pass


class InvalidTopicError(ResearchAssistantError):
    """Raised when an invalid, empty, or unparseable research topic is provided."""
    pass


class ToolExecutionError(ResearchAssistantError):
    """Raised when an agent tool fails to execute cleanly."""
    pass


class ModelInferenceError(ResearchAssistantError):
    """Raised when model inference fails repeatedly or returns unparseable outputs."""
    pass


class ReportGenerationError(ResearchAssistantError):
    """Raised when saving or rendering the research dossier fails."""
    pass


class RateLimitExceededError(ResearchAssistantError):
    """Raised when external search or LLM APIs encounter rate limits."""
    pass
