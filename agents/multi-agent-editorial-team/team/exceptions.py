"""Exception hierarchy for the Multi-Agent Editorial Team."""


class EditorialTeamError(Exception):
    """Base exception for all editorial team pipeline errors."""
    pass


class InvalidTopicError(EditorialTeamError):
    """Raised when an empty or invalid topic is provided."""
    pass


class AgentExecutionError(EditorialTeamError):
    """Raised when an individual specialized agent fails execution."""
    pass


class MaxRevisionsExceededError(EditorialTeamError):
    """Raised when revision loop exceeds safety circuit breaker limit without consensus."""
    pass


class PipelineHaltError(EditorialTeamError):
    """Raised when a catastrophic pipeline failure occurs."""
    pass
