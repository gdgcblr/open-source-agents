"""Tool functions shared by the ADK agent and the MCP server.

Kept free of `from __future__ import annotations` so ADK and MCP can read the
real type hints when they build tool schemas. Every function returns plain
JSON-serialisable data and never raises for expected failures, so the calling
model always gets something it can explain to the user.
"""

from typing import Any, Dict, List, Optional

from .github import GitHubClient, GitHubError
from .models import Profile
from .scout import Scout

_client: Optional[GitHubClient] = None
_BODY_LIMIT = 1500


def _scout() -> Scout:
    # One client per process so repeated tool calls reuse the response cache.
    global _client
    if _client is None:
        _client = GitHubClient()
    return Scout(_client)


def _error(exc: Exception) -> Dict[str, Any]:
    return {"error": str(exc)}


def find_issues(
    languages: List[str],
    topics: Optional[List[str]] = None,
    hours: float = 3.0,
    limit: int = 5,
    github_user: str = "",
    min_stars: int = 100,
) -> Dict[str, Any]:
    """Find open beginner-friendly GitHub issues that are genuinely available to work on.

    Filters out issues that are assigned, already have an open or merged PR, or that a
    maintainer says are fixed. Ranks the rest by freshness, whether the repo actually
    merges outside PRs, competition from other claimants, and fit to the time available.

    Args:
        languages: Programming languages the contributor knows, e.g. ["python", "typescript"].
            Pass an empty list together with github_user to infer them.
        topics: Optional GitHub repository topics to focus on, e.g. ["machine-learning"].
        hours: Roughly how many hours the contributor can spend.
        limit: How many issues to return (1-10).
        github_user: Optional GitHub username; their public repos are used to infer languages.
        min_stars: Ignore repositories with fewer stars than this.

    Returns:
        A dict with "candidates" (ranked, each with verdict, score, reasons, flags and
        evidence links), "skip_summary" (why issues were filtered out) and "notes".
    """
    scout = _scout()
    try:
        if github_user and not languages:
            profile = scout.profile_from_user(github_user, topics=topics or [], hours=hours, min_stars=min_stars)
        else:
            profile = Profile(languages=languages, topics=topics or [], hours=hours, min_stars=min_stars)
        result = scout.find(profile, limit=max(1, min(int(limit), 10)))
    except GitHubError as exc:
        return _error(exc)
    data = result.to_dict()
    data.pop("skipped", None)
    return data


def inspect_issue(issue: str, hours: float = 3.0) -> Dict[str, Any]:
    """Check whether one GitHub issue is a good, still-available pick before starting work.

    Args:
        issue: Issue URL (https://github.com/owner/repo/issues/123) or "owner/repo#123".
        hours: Roughly how many hours the contributor can spend.

    Returns:
        Verdict (ready, caution or skip), score, reasons, flags, the claims, linked PRs and
        "already fixed" comments that were found, and repository merge statistics.
    """
    try:
        candidate = _scout().inspect(issue, Profile(languages=[], hours=hours))
    except (GitHubError, ValueError) as exc:
        return _error(exc)
    data = candidate.to_dict(include_body=True)
    data["body"] = data["body"][:_BODY_LIMIT]
    return data


def related_issues(issue: str) -> Dict[str, Any]:
    """Find open and closed issues and merged PRs related to a GitHub issue.

    Use this to spot duplicates and to learn from PRs that fixed similar problems.

    Args:
        issue: Issue URL or "owner/repo#123".

    Returns:
        A dict with "open_issues", "closed_issues" and "merged_prs", each a list of
        {number, title, url, state, similarity, possible_duplicate}.
    """
    try:
        related = _scout().related(issue)
    except (GitHubError, ValueError) as exc:
        return _error(exc)
    return {key: [vars(item) for item in items] for key, items in related.items()}


def repo_conventions(repo: str) -> Dict[str, Any]:
    """Read a repository's contributing guide and pull out the rules newcomers often miss.

    Args:
        repo: Repository in "owner/name" form.

    Returns:
        Rules such as CLA, DCO sign-off, Conventional Commits or changelog entries, plus
        setup, test and lint commands found in the guide.
    """
    try:
        return _scout().conventions(repo)
    except GitHubError as exc:
        return _error(exc)


def starter_brief_facts(issue: str, hours: float = 3.0) -> Dict[str, Any]:
    """Gather everything needed to plan a first PR for an issue.

    Combines the availability check, related issues and PRs, contributing rules and the
    repository files most likely to need changes.

    Args:
        issue: Issue URL or "owner/repo#123".
        hours: Roughly how many hours the contributor can spend.

    Returns:
        A dict with "issue", "evidence", "keywords", "related", "conventions" and "likely_files".
    """
    try:
        facts = _scout().brief_facts(issue, Profile(languages=[], hours=hours))
    except (GitHubError, ValueError) as exc:
        return _error(exc)
    facts["issue"]["body"] = facts["issue"]["body"][:_BODY_LIMIT]
    return facts


ALL_TOOLS = [find_issues, inspect_issue, related_issues, repo_conventions, starter_brief_facts]
