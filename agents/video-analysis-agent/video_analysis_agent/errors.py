"""Exception types. All inherit AgentError so the CLI can show a clean message."""


class AgentError(Exception):
    """Base class for expected, user-presentable failures."""


class ConfigError(AgentError):
    """Missing or invalid configuration (API keys, provider, options)."""


class VideoError(AgentError):
    """Unsupported/corrupt input, missing FFmpeg, or audio extraction failure."""


class TranscriptionError(AgentError):
    """Speech-to-text failed or found no speech."""


class LLMError(AgentError):
    """The LLM API call failed (auth, rate limit, network, bad response)."""


class AnalysisError(AgentError):
    """The LLM output could not be turned into a valid analysis."""
