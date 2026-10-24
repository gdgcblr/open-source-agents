"""Shared read-only HTTP helper: GET only, timeouts, one retry, clear errors."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import requests

from .errors import AuthError, InvalidInputError, NotFoundError, RateLimitError, UpstreamError

DEFAULT_TIMEOUT = 10.0
USER_AGENT = "good-first-issue-agent/0.1 (+https://github.com/gdgcblr/open-source-agents)"


def _reset_hint(headers: Any) -> str:
    reset = headers.get("X-RateLimit-Reset") or headers.get("X-Sentry-Rate-Limit-Reset")
    retry_after = headers.get("Retry-After")
    if reset and str(reset).isdigit():
        when = datetime.fromtimestamp(int(reset), tz=timezone.utc)
        return f" The limit resets at {when:%H:%M} UTC."
    if retry_after and str(retry_after).isdigit():
        return f" Retry after {retry_after} seconds."
    return ""


def get_json(
    session: requests.Session,
    url: str,
    *,
    service: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    not_found: str = "Not found.",
    retries: int = 1,
) -> tuple[Any, requests.Response]:
    """GET a URL and return (parsed JSON, response).

    Errors are mapped to AgentError subclasses. Messages include the service name
    and status, never request headers (which may hold a token).
    """
    all_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    all_headers.update(headers or {})

    attempt = 0
    while True:
        attempt += 1
        try:
            resp = session.get(url, params=params, headers=all_headers, timeout=timeout)
        except requests.exceptions.SSLError:
            raise UpstreamError(
                f"Could not verify {service}'s TLS certificate. A proxy or firewall may be intercepting "
                "HTTPS; set REQUESTS_CA_BUNDLE to your organization's CA certificate file."
            )
        except requests.Timeout:
            if attempt <= retries:
                continue
            raise UpstreamError(f"{service} did not respond within {timeout:g}s. Try again later.")
        except requests.ConnectionError:
            if attempt <= retries:
                time.sleep(0.5)
                continue
            raise UpstreamError(f"Could not connect to {service}. Check your network connection.")
        except requests.RequestException as exc:  # pragma: no cover - rare
            raise UpstreamError(f"Request to {service} failed: {type(exc).__name__}.")

        status = resp.status_code
        if 500 <= status < 600 and attempt <= retries:
            time.sleep(1.0)
            continue
        break

    if status == 404:
        raise NotFoundError(not_found)
    if status == 401:
        raise AuthError(f"{service} rejected the token (401). Check that it is valid and not expired.")
    if status == 429 or (status == 403 and resp.headers.get("X-RateLimit-Remaining") == "0"):
        raise RateLimitError(
            f"{service} rate limit reached.{_reset_hint(resp.headers)}"
            + (" Setting GITHUB_TOKEN raises the limit from 60 to 5,000 requests/hour." if service == "GitHub" else "")
        )
    if status == 403:
        raise AuthError(f"{service} refused access (403). The token may lack the required permission.")
    if status == 410:
        raise NotFoundError(f"{service}: this resource is gone or disabled (410). {not_found}")
    if status == 400:
        detail = ""
        try:
            body = resp.json()
            if isinstance(body, dict) and isinstance(body.get("detail"), str):
                detail = " " + body["detail"][:200]
        except ValueError:
            pass
        raise InvalidInputError(f"{service} rejected the request (400).{detail}")
    if 500 <= status < 600:
        raise UpstreamError(f"{service} returned a server error ({status}). Try again later.")
    if status >= 400:
        raise UpstreamError(f"{service} returned an unexpected status ({status}).")

    try:
        return resp.json(), resp
    except ValueError:
        raise UpstreamError(f"{service} returned a response that is not valid JSON.")
