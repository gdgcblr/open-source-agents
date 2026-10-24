"""Error types shown to the user. Messages must never contain tokens or keys."""


class AgentError(Exception):
    """Base class for errors that the CLI reports cleanly (no traceback)."""

    exit_code = 1


class InvalidInputError(AgentError):
    """The user gave a repository, project, or option we cannot use."""

    exit_code = 2


class NotFoundError(AgentError):
    """The repository, project, or issue does not exist or is not visible."""


class AuthError(AgentError):
    """The token is missing, invalid, or lacks permission."""


class RateLimitError(AgentError):
    """The upstream API refused the request because of rate limiting."""


class UpstreamError(AgentError):
    """Network failure, timeout, server error, or an unexpected response."""


class AIUnavailableError(AgentError):
    """Model-assisted mode cannot run (missing package, key, or model failure)."""
