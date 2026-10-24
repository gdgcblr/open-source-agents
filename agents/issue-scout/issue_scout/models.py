"""Plain data containers shared by the scout, the CLI, the MCP server and the ADK agent."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

BEGINNER_LABELS = ["good first issue", "help wanted"]


@dataclass
class Profile:
    """What the contributor knows and how much time they have."""

    languages: List[str]
    topics: List[str] = field(default_factory=list)
    hours: float = 3.0
    labels: List[str] = field(default_factory=lambda: list(BEGINNER_LABELS))
    min_stars: int = 100
    max_stars: Optional[int] = None


@dataclass
class Mention:
    """A comment or event that matters for the verdict, with a link for proof."""

    author: str
    created_at: str
    url: str
    quote: str = ""
    is_maintainer: bool = False


@dataclass
class PullRef:
    number: int
    url: str
    title: str
    state: str  # "open", "merged" or "closed"
    author: str = ""


@dataclass
class IssueSignals:
    assignees: List[str] = field(default_factory=list)
    active_claims: List[Mention] = field(default_factory=list)
    stale_claims: List[Mention] = field(default_factory=list)
    resolved_hints: List[Mention] = field(default_factory=list)
    open_policy: Optional[Mention] = None
    injection_hints: List[Mention] = field(default_factory=list)
    pulls: List[PullRef] = field(default_factory=list)
    maintainer_comments: int = 0
    last_maintainer_comment: Optional[str] = None

    def pulls_with_state(self, state: str) -> List[PullRef]:
        return [p for p in self.pulls if p.state == state]


@dataclass
class RepoHealth:
    full_name: str
    stars: int = 0
    pushed_at: str = ""
    archived: bool = False
    description: str = ""
    default_branch: str = "main"
    closed_sample: int = 0
    outside_merged: int = 0
    outside_closed_unmerged: int = 0
    median_merge_days: Optional[float] = None

    @property
    def outside_merge_ratio(self) -> Optional[float]:
        total = self.outside_merged + self.outside_closed_unmerged
        return None if total == 0 else self.outside_merged / total


@dataclass
class Candidate:
    repo: str
    number: int
    title: str
    url: str
    labels: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    comments: int = 0
    body: str = ""
    locked: bool = False
    signals: Optional[IssueSignals] = None
    repo_health: Optional[RepoHealth] = None
    verdict: str = "unknown"  # "ready", "caution" or "skip"
    score: int = 0
    effort: str = "unknown"  # "small", "medium" or "large"
    reasons: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)

    @property
    def ref(self) -> str:
        return "%s#%d" % (self.repo, self.number)

    def to_dict(self, include_body: bool = False) -> Dict[str, Any]:
        data = dataclasses.asdict(self)
        data["ref"] = self.ref
        if self.repo_health is not None:
            data["repo_health"]["outside_merge_ratio"] = self.repo_health.outside_merge_ratio
        if not include_body:
            data.pop("body", None)
        return data


@dataclass
class ScoutResult:
    profile: Profile
    candidates: List[Candidate]
    skipped: List[Candidate]
    repos_considered: int
    requests_made: int
    notes: List[str] = field(default_factory=list)

    def skip_summary(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for candidate in self.skipped:
            for flag in candidate.flags:
                if flag in SKIP_FLAGS:
                    counts[flag] = counts.get(flag, 0) + 1
        return counts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": dataclasses.asdict(self.profile),
            "candidates": [c.to_dict() for c in self.candidates],
            "skipped": [c.to_dict() for c in self.skipped],
            "skip_summary": self.skip_summary(),
            "repos_considered": self.repos_considered,
            "requests_made": self.requests_made,
            "notes": self.notes,
        }


# Flags that make an issue a dead end for a newcomer.
SKIP_FLAGS = {
    "closed": "the issue is already closed",
    "open-pr": "someone already has an open PR for it",
    "merged-pr": "a linked PR was already merged",
    "assigned": "it is assigned to someone",
    "likely-resolved": "a maintainer says it is already fixed or a duplicate",
    "repo-archived": "the repository is archived",
    "locked": "the conversation is locked",
}

# Short forms for the "filtered out N dead ends" summary line.
SKIP_SUMMARY = {
    "closed": "were closed",
    "open-pr": "already had an open PR",
    "merged-pr": "had a merged PR",
    "assigned": "were assigned",
    "likely-resolved": "were reported fixed by a maintainer",
    "repo-archived": "were in archived repos",
    "locked": "were locked",
}

# Flags that are worth knowing about but do not rule the issue out.
CAUTION_FLAGS = {
    "possibly-resolved": "a contributor says it may already be fixed; confirm first",
    "recently-claimed": "someone asked to work on it recently",
    "previous-attempt-closed": "an earlier PR was closed without merging",
    "needs-decision": "labelled as an RFC/discussion; maintainers must decide first",
    "suspicious-instructions": "contains text aimed at AI tools (possible prompt injection); treated as data",
    "old-issue": "opened more than two years ago",
    "busy-thread": "long discussion; read it before starting",
    "slow-merges": "outside PRs take a long time to merge here",
    "no-outside-merges": "no recent PRs from outside contributors were merged",
    "may-exceed-time": "probably more work than the time you have",
}
