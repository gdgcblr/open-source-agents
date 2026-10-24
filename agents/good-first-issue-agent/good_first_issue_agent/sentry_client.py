"""Read-only client for Sentry and GlitchTip (GlitchTip implements the Sentry API).

Endpoints used (GET only):
- Sentry:    /api/0/organizations/{org}/issues/?project={slug}
- GlitchTip: /api/0/projects/{org}/{project}/issues/
- Both:      /api/0/organizations/{org}/issues/{id}/
- Both:      /api/0/organizations/{org}/issues/{id}/events/latest/

Error-tracker data is private and may contain personal data. Titles, messages
and stack traces are masked (emails, IPs, secrets) when normalized. Local
variables, request data, user data and breadcrumbs are never read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse

import requests

from .errors import InvalidInputError, NotFoundError
from .guardrails import SLUG_RE, clean
from .http_client import DEFAULT_TIMEOUT, get_json
from .models import Issue

DEFAULT_BASE_URLS = {"sentry": "https://sentry.io", "glitchtip": "https://app.glitchtip.com"}
MAX_PAGES = 3
MAX_LIMIT = 50
TEXT_LIMIT = 500


@dataclass
class TrackerRef:
    kind: str  # "sentry" or "glitchtip"
    base_url: str
    org: str
    project: str

    @property
    def full_name(self) -> str:
        return f"{self.org}/{self.project}"

    @property
    def service(self) -> str:
        return "Sentry" if self.kind == "sentry" else "GlitchTip"


def make_tracker_ref(kind: str, base_url: str | None, org: str | None, project: str | None) -> TrackerRef:
    if kind not in DEFAULT_BASE_URLS:
        raise InvalidInputError(f"Unknown error tracker '{kind}'.")
    name = "Sentry" if kind == "sentry" else "GlitchTip"
    if not org or not project:
        raise InvalidInputError(
            f"{name} needs an organization and a project: use --org and --project "
            f"(or {kind.upper()}_ORG and {kind.upper()}_PROJECT in .env)."
        )
    for label, value in (("organization", org), ("project", project)):
        if not SLUG_RE.match(value):
            raise InvalidInputError(f"'{value}' is not a valid {name} {label} slug.")

    url = (base_url or DEFAULT_BASE_URLS[kind]).strip().rstrip("/")
    if url.endswith("/api/0"):
        url = url[: -len("/api/0")]
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host or parsed.scheme not in ("http", "https"):
        raise InvalidInputError(f"'{url}' is not a valid {name} URL (expected e.g. https://glitchtip.example.com).")
    if parsed.scheme == "http" and host not in ("localhost", "127.0.0.1", "::1"):
        raise InvalidInputError(f"Refusing to send a token over plain http to {host}. Use https.")
    return TrackerRef(kind=kind, base_url=f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}", org=org, project=project)


def parse_issue_id(value: str | int) -> str:
    text = str(value).strip()
    if not text.isdigit() or len(text) > 20:
        raise InvalidInputError(
            f"'{value}' is not a numeric issue id. Use the number from the issue URL "
            "(e.g. .../issues/123456/), not the short id."
        )
    return text


class ErrorTrackerClient:
    def __init__(
        self,
        ref: TrackerRef,
        *,
        token: str | None,
        session: requests.Session | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        stats_period: str = "14d",
    ) -> None:
        if not token:
            env = "SENTRY_AUTH_TOKEN" if ref.kind == "sentry" else "GLITCHTIP_AUTH_TOKEN"
            raise InvalidInputError(
                f"{ref.service} always needs an auth token with read access (event:read). Set {env} in .env."
            )
        self.ref = ref
        self.timeout = timeout
        self.stats_period = stats_period
        self.session = session or requests.Session()
        self._headers = {"Authorization": f"Bearer {token}"}
        self._api = f"{ref.base_url}/api/0"
        self._origin = urlparse(ref.base_url)

    def _get(self, url: str, *, params: dict[str, Any] | None = None, not_found: str) -> tuple[Any, Any]:
        return get_json(
            self.session, url, service=self.ref.service, params=params,
            headers=self._headers, timeout=self.timeout, not_found=not_found,
        )

    def _same_origin(self, url: str) -> bool:
        """Only follow pagination links to the configured host, so the token never leaves it."""
        p = urlparse(url)
        return p.scheme == self._origin.scheme and p.netloc == self._origin.netloc

    @property
    def _org(self) -> str:
        return quote(self.ref.org)

    def _project_not_found(self) -> str:
        return (
            f"{self.ref.service} project {self.ref.full_name} was not found at {self.ref.base_url}, "
            "or the token cannot see it."
        )

    def list_issues(self, *, limit: int = 20, query: str = "is:unresolved") -> list[Issue]:
        limit = max(1, min(limit, MAX_LIMIT))
        if self.ref.kind == "sentry":
            url = f"{self._api}/organizations/{self._org}/issues/"
            params: dict[str, Any] | None = {
                "project": self.ref.project, "query": query, "limit": limit,
                "sort": "date", "statsPeriod": self.stats_period,
            }
        else:
            url = f"{self._api}/projects/{self._org}/{quote(self.ref.project)}/issues/"
            params = {"query": query, "limit": limit}

        issues: list[Issue] = []
        for _ in range(MAX_PAGES):
            data, resp = self._get(url, params=params, not_found=self._project_not_found())
            if not isinstance(data, list):
                break
            for raw in data:
                if isinstance(raw, dict):
                    issues.append(self._to_issue(raw))
                    if len(issues) >= limit:
                        return issues
            nxt = (getattr(resp, "links", None) or {}).get("next") or {}
            if not nxt.get("url") or nxt.get("results") == "false" or not self._same_origin(nxt["url"]):
                break
            url, params = nxt["url"], None
        return issues

    def get_issue(self, issue_id: str) -> Issue:
        issue_id = parse_issue_id(issue_id)
        data, _ = self._get(
            f"{self._api}/organizations/{self._org}/issues/{issue_id}/",
            not_found=f"{self.ref.service} issue {issue_id} was not found in {self.ref.org}.",
        )
        if not isinstance(data, dict):
            raise NotFoundError(f"{self.ref.service} issue {issue_id} was not found.")
        issue = self._to_issue(data)
        project = data.get("project") or {}
        if isinstance(project, dict) and project.get("slug") and project["slug"] != self.ref.project:
            raise InvalidInputError(
                f"Issue {issue_id} belongs to project '{project['slug']}', not '{self.ref.project}'."
            )
        return issue

    def get_latest_event(self, issue_id: str, *, max_frames: int = 15) -> dict[str, Any]:
        """Exception types/messages and stack frames (file, function, line, in_app) of
        the latest event. Local variables, request, user and breadcrumb data are skipped."""
        issue_id = parse_issue_id(issue_id)
        data, _ = self._get(
            f"{self._api}/organizations/{self._org}/issues/{issue_id}/events/latest/",
            not_found=f"No events found for {self.ref.service} issue {issue_id}.",
        )
        if not isinstance(data, dict):
            return {"exceptions": [], "frames": []}
        return parse_event(data, max_frames=max_frames)

    def _to_issue(self, raw: dict[str, Any]) -> Issue:
        meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        assigned = raw.get("assignedTo")
        assignees = []
        if isinstance(assigned, dict):
            assignees.append(str(assigned.get("name") or assigned.get("email") or "someone"))
        elif assigned:
            assignees.append(str(assigned))
        culprit = clean(raw.get("culprit") or "", 200)
        error_type = clean(str(meta.get("type") or ""), 120)
        error_value = clean(str(meta.get("value") or ""), TEXT_LIMIT)
        stack_files = [f for f in [str(meta.get("filename") or "")] if f and not f.startswith("<")]
        body_lines = [
            f"Error type: {error_type}" if error_type else "",
            f"Message: {error_value}" if error_value else "",
            f"Culprit: {culprit}" if culprit else "",
            f"File: {stack_files[0]}" if stack_files else "",
            f"Function: {clean(str(meta.get('function') or ''), 120)}" if meta.get("function") else "",
        ]
        try:
            count = int(raw.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        return Issue(
            source=self.ref.kind,
            id=str(raw.get("id") or ""),
            display_id=str(raw.get("shortId") or raw.get("id") or "?"),
            title=clean(raw.get("title") or "(no title)", 200),
            url=raw.get("permalink") or "",
            body="\n".join(line for line in body_lines if line),
            labels=[],
            state=str(raw.get("status") or "unresolved"),
            assignees=assignees,
            comments=int(raw.get("numComments") or 0),
            created_at=str(raw.get("firstSeen") or ""),
            updated_at=str(raw.get("lastSeen") or ""),
            level=str(raw.get("level") or ""),
            culprit=culprit,
            event_count=count,
            user_count=int(raw.get("userCount") or 0),
            error_type=error_type,
            error_value=error_value,
            stack_files=stack_files,
        )


def parse_event(data: dict[str, Any], *, max_frames: int = 15) -> dict[str, Any]:
    """Pull exception info out of a Sentry/GlitchTip event (the `entries` format,
    falling back to a top-level `exception`)."""
    values: list[dict[str, Any]] = []
    for entry in data.get("entries") or []:
        if isinstance(entry, dict) and entry.get("type") == "exception":
            values = ((entry.get("data") or {}).get("values")) or []
            break
    if not values and isinstance(data.get("exception"), dict):
        values = data["exception"].get("values") or []

    exceptions, frames = [], []
    for exc in values if isinstance(values, list) else []:
        if not isinstance(exc, dict):
            continue
        exceptions.append({
            "type": clean(str(exc.get("type") or ""), 120),
            "value": clean(str(exc.get("value") or ""), TEXT_LIMIT),
        })
        stack = exc.get("stacktrace") or {}
        for fr in (stack.get("frames") or []) if isinstance(stack, dict) else []:
            if not isinstance(fr, dict):
                continue
            filename = fr.get("filename") or fr.get("absPath") or fr.get("abs_path") or fr.get("module") or ""
            frames.append({
                "file": clean(str(filename), 200),
                "function": clean(str(fr.get("function") or ""), 120),
                "line": fr.get("lineNo") if fr.get("lineNo") is not None else fr.get("lineno"),
                "in_app": bool(fr.get("inApp") if "inApp" in fr else fr.get("in_app")),
            })
    # Innermost frames are last; keep the most relevant ones, preferring application code.
    in_app = [f for f in frames if f["in_app"]]
    chosen = (in_app or frames)[-max_frames:]
    return {
        "exceptions": exceptions[-3:],
        "frames": list(reversed(chosen)),  # innermost first
        "platform": str(data.get("platform") or ""),
        "release": clean(str((data.get("release") or {}).get("version") or "") if isinstance(data.get("release"), dict) else str(data.get("release") or ""), 80),
        "environment": next(
            (clean(str(t.get("value")), 60) for t in (data.get("tags") or [])
             if isinstance(t, dict) and t.get("key") == "environment"),
            "",
        ),
    }
