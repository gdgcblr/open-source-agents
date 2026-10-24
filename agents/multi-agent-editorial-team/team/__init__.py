"""Multi-Agent Editorial Team Package."""

from .state import (
    AgentRole,
    ReviewStatus,
    CritiqueItem,
    ReviewVerdict,
    EvidenceItem,
    ArticlePlan,
    AgentMessage,
    EditorialMetrics,
    TeamState,
)
from .exceptions import (
    EditorialTeamError,
    InvalidTopicError,
    AgentExecutionError,
    MaxRevisionsExceededError,
)

__all__ = [
    "AgentRole",
    "ReviewStatus",
    "CritiqueItem",
    "ReviewVerdict",
    "EvidenceItem",
    "ArticlePlan",
    "AgentMessage",
    "EditorialMetrics",
    "TeamState",
    "EditorialTeamError",
    "InvalidTopicError",
    "AgentExecutionError",
    "MaxRevisionsExceededError",
]
