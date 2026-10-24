"""GitHub activity tool.

This is the "external capability" the LLM does not have on its own: it reaches
out to the GitHub REST API and returns verifiable events (commits, PRs, issues,
reviews) for a given user and day.

Design notes:
* Each source is fetched independently. If one fails we record a warning and
  mark the log ``partial`` instead of silently dropping data, because a partial
  log is exactly the situation that should trigger escalation, not a confident
  (and wrong) "nothing to report".
* No LLM involvement here. The tool only returns facts.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import requests

from .models import ActivityEvent, ActivityLog

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
_TIMEOUT = 20


class GitHubTool:
    def __init__(self, token: str | None = None, session: requests.Session | None = None):
        self.token = token or os.getenv("GITHUB_TOKEN") or ""
        self.session = session or requests.Session()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.session.headers.update(headers)

    # -- public API ---------------------------------------------------------

    def fetch_day(self, username: str, date: str) -> ActivityLog:
        """Return everything ``username`` did on ``date`` (ISO ``YYYY-MM-DD``).

        ``username`` is normalized first, so a full profile URL
        (``https://github.com/foo``) or an ``@foo`` handle all resolve to
        ``foo``. This makes the tool forgiving of how a user pastes an identity.
        """
        username = _normalize_username(username)
        log = ActivityLog(username=username, date=date)
        start, end = _day_bounds(date)

        # The public Events API is the cheapest way to get a day of activity.
        try:
            events = self._fetch_events(username)
            for ev in events:
                parsed = _parse_event(ev, start, end)
                if parsed is not None:
                    log.events.append(parsed)
        except Exception as exc:  # noqa: BLE001 - surface as a warning, not a crash
            logger.warning("events fetch failed: %s", exc)
            log.fetch_warnings.append(f"Could not fetch activity events: {exc}")
            log.partial = True

        # De-duplicate (the events feed can repeat) and sort chronologically.
        seen: dict[str, ActivityEvent] = {}
        for e in log.events:
            seen[e.event_id] = e
        log.events = sorted(seen.values(), key=lambda e: e.timestamp)
        return log

    # -- internals ----------------------------------------------------------

    def _fetch_events(self, username: str) -> list[dict[str, Any]]:
        """Pull recent public + accessible events for the user (paginated)."""
        results: list[dict[str, Any]] = []
        for page in range(1, 4):  # up to 300 events; plenty for one day
            url = f"{GITHUB_API}/users/{username}/events"
            resp = self.session.get(url, params={"per_page": 100, "page": page},
                                     timeout=_TIMEOUT)
            if resp.status_code == 404:
                raise RuntimeError(f"user '{username}' not found")
            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                raise RuntimeError("GitHub rate limit hit (set GITHUB_TOKEN)")
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            results.extend(batch)
        return results


def _normalize_username(raw: str) -> str:
    """Turn user-pasted identity into a bare GitHub login.

    Accepts: 'foo', '@foo', 'github.com/foo', 'https://github.com/foo',
    'https://github.com/foo/' and strips any trailing path/query.
    """
    s = (raw or "").strip()
    if not s:
        return s
    s = s.lstrip("@")
    # Drop a scheme if present.
    s = re.sub(r"^https?://", "", s, flags=re.IGNORECASE)
    # If it looks like a github.com URL, take the first path segment.
    if s.lower().startswith("github.com/"):
        s = s[len("github.com/"):]
    # Keep only the first path component (the login), drop query/fragment.
    s = s.split("/")[0].split("?")[0].split("#")[0]
    return s.strip()


def _day_bounds(date: str) -> tuple[datetime, datetime]:
    start = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
    end = start.replace(hour=23, minute=59, second=59)
    return start, end


def _in_window(ts: datetime, start: datetime, end: datetime) -> bool:
    return start <= ts <= end


def _parse_ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _parse_event(ev: dict[str, Any], start: datetime, end: datetime) -> ActivityEvent | None:
    """Translate a raw GitHub event into one of our typed records.

    Returns ``None`` if the event is outside the day window or of a kind we do
    not summarize. We deliberately map only the event types that represent
    concrete, attributable work.
    """
    etype = ev.get("type")
    created = ev.get("created_at")
    if not created:
        return None
    ts = _parse_ts(created)
    if not _in_window(ts, start, end):
        return None

    repo = ev.get("repo", {}).get("name", "unknown/unknown")
    payload = ev.get("payload", {})

    if etype == "PushEvent":
        commits = payload.get("commits", [])
        ref = (payload.get("ref") or "").replace("refs/heads/", "")
        size = payload.get("size", len(commits))
        if commits:
            # Represent the most recent commit of the push as the event; the
            # rest are summarized in extra so the model can mention the count
            # truthfully.
            head = commits[-1]
            sha = head.get("sha", "")[:7]
            msg = (head.get("message") or "").splitlines()[0][:140]
            return ActivityEvent(
                event_id=f"commit:{sha}" if sha else f"push:{repo}:{created}",
                kind="commit",
                repo=repo,
                title=msg or "(no message)",
                url=f"https://github.com/{repo}/commit/{head.get('sha','')}",
                timestamp=ts,
                extra={"commit_count": len(commits), "ref": ref},
            )
        # GitHub often returns a PushEvent with an empty `commits` array (large
        # pushes, merges, or trimmed payloads). This is still real, attributable
        # work, so we record it using the push head SHA rather than dropping it.
        head_sha = (payload.get("head") or "")[:7]
        count = size if isinstance(size, int) and size > 0 else 1
        plural = "s" if count != 1 else ""
        branch = f" to {ref}" if ref else ""
        return ActivityEvent(
            event_id=f"push:{repo}@{head_sha}" if head_sha else f"push:{repo}:{created}",
            kind="commit",
            repo=repo,
            title=f"Pushed {count} commit{plural}{branch}",
            url=(
                f"https://github.com/{repo}/commit/{payload.get('head','')}"
                if head_sha
                else f"https://github.com/{repo}"
            ),
            timestamp=ts,
            extra={"commit_count": count, "ref": ref, "detail": "summary"},
        )

    if etype == "PullRequestEvent":
        pr = payload.get("pull_request", {})
        num = payload.get("number") or pr.get("number")
        action = payload.get("action", "")
        state = "merged" if pr.get("merged") else pr.get("state", action)
        return ActivityEvent(
            event_id=f"pr:{repo}#{num}",
            kind="pull_request",
            repo=repo,
            title=pr.get("title", f"PR #{num}")[:160],
            url=pr.get("html_url", f"https://github.com/{repo}/pull/{num}"),
            timestamp=ts,
            state=str(state),
            extra={"action": action},
        )

    if etype == "IssuesEvent":
        issue = payload.get("issue", {})
        num = issue.get("number")
        return ActivityEvent(
            event_id=f"issue:{repo}#{num}",
            kind="issue",
            repo=repo,
            title=issue.get("title", f"Issue #{num}")[:160],
            url=issue.get("html_url", f"https://github.com/{repo}/issues/{num}"),
            timestamp=ts,
            state=str(payload.get("action", issue.get("state", ""))),
        )

    if etype == "PullRequestReviewEvent":
        pr = payload.get("pull_request", {})
        num = pr.get("number")
        return ActivityEvent(
            event_id=f"review:{repo}#{num}",
            kind="review",
            repo=repo,
            title=f"Reviewed PR: {pr.get('title', f'#{num}')}"[:160],
            url=pr.get("html_url", f"https://github.com/{repo}/pull/{num}"),
            timestamp=ts,
            state=str(payload.get("review", {}).get("state", "")),
        )

    if etype == "IssueCommentEvent":
        issue = payload.get("issue", {})
        num = issue.get("number")
        # An issue with a pull_request key is really a PR thread.
        is_pr = "pull_request" in issue
        noun = "PR" if is_pr else "issue"
        return ActivityEvent(
            event_id=f"comment:{repo}#{num}",
            kind="review",
            repo=repo,
            title=f"Commented on {noun} #{num}: {issue.get('title', '')}"[:160],
            url=issue.get("html_url", f"https://github.com/{repo}/issues/{num}"),
            timestamp=ts,
            state=str(payload.get("action", "created")),
        )

    if etype == "CreateEvent":
        # Creating a branch, tag, or repository.
        ref_type = payload.get("ref_type", "ref")  # branch | tag | repository
        ref = payload.get("ref")
        if ref_type == "repository" or not ref:
            title = f"Created repository {repo}"
            key = "repo"
        else:
            title = f"Created {ref_type} '{ref}' in {repo}"
            key = f"{ref_type}:{ref}"
        return ActivityEvent(
            event_id=f"create:{repo}:{key}",
            kind="create",
            repo=repo,
            title=title[:160],
            url=f"https://github.com/{repo}",
            timestamp=ts,
            state=ref_type,
        )

    if etype == "DeleteEvent":
        ref_type = payload.get("ref_type", "ref")
        ref = payload.get("ref", "")
        return ActivityEvent(
            event_id=f"delete:{repo}:{ref_type}:{ref}",
            kind="delete",
            repo=repo,
            title=f"Deleted {ref_type} '{ref}' in {repo}"[:160],
            url=f"https://github.com/{repo}",
            timestamp=ts,
            state=ref_type,
        )

    return None
