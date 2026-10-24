"""Ingestion package for local fixtures, read-only GitHub PRs, and bounded snapshots."""

from patchproof.ingestion.fixture_loader import (
    FixtureIngestionError,
    PathTraversalError,
    load_fixture_snapshot,
    resolve_confined_path,
)
from patchproof.ingestion.github_loader import (
    GitHubIngestionError,
    GitHubRateLimitError,
    GitHubURLValidationError,
    ParsedGitHubPRUrl,
    load_github_pr_snapshot,
    parse_github_pr_url,
)
from patchproof.ingestion.snapshot import ContextSnapshot, FileSnapshot

__all__ = [
    "ContextSnapshot",
    "FileSnapshot",
    "FixtureIngestionError",
    "GitHubIngestionError",
    "GitHubRateLimitError",
    "GitHubURLValidationError",
    "ParsedGitHubPRUrl",
    "PathTraversalError",
    "load_fixture_snapshot",
    "load_github_pr_snapshot",
    "parse_github_pr_url",
    "resolve_confined_path",
]


