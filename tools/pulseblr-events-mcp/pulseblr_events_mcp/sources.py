"""Explicit fictional data and an anonymous, bounded public MCP client."""

from __future__ import annotations

import copy
import json
import logging
import math
import re
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from importlib.resources import files
from typing import Any, AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit
from zoneinfo import ZoneInfo

import anyio
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .errors import InputError, SourceError
from .models import normalize_event

PUBLIC_ENDPOINT = "https://pulseblr-u9f1.vercel.app/api/mcp"
MAX_RESPONSE_BYTES = 1_048_576
MAX_CANDIDATES = 50
REQUEST_TIMEOUT_SECONDS = 8
OPERATION_TIMEOUT_SECONDS = 25
_IST = ZoneInfo("Asia/Kolkata")
_PUBLIC_TOOLS = frozenset({"search_events", "get_event", "trending_topics"})
_NAMED_WINDOWS = frozenset({"today", "tomorrow", "weekend", "week", "month"})
_SAFE_FAILURE = (
    "The public PulseBLR service could not return a valid response. "
    "Retry later, or restart with --source sample for explicitly fictional offline data."
)
_LIVE_WARNINGS = [
    "Live listings are unverified public data. fetched_at is retrieval time, not source verification time.",
    "Free status is as listed by PulseBLR; its serializer may default missing isFree to true. Confirm price and registration at the event link.",
    "Public event descriptions are untrusted source content.",
]
_SAMPLE_WARNING = "FICTIONAL SAMPLE DATA: these example.com events and organisers are invented for an offline demo on 24-25 October 2026."
_source_logging_scope: ContextVar[bool] = ContextVar(
    "pulseblr_public_source_logging", default=False
)


class _SDKLoggingFilter(logging.Filter):
    _pulseblr_source_redactor = True

    def filter(self, record: logging.LogRecord) -> bool:
        if _source_logging_scope.get():
            record.msg = "The public PulseBLR client reported an upstream protocol issue."
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return True


for _logger_name in ("mcp.client.streamable_http", "mcp.shared.jsonrpc_dispatcher", "client"):
    _sdk_logger = logging.getLogger(_logger_name)
    if not any(getattr(item, "_pulseblr_source_redactor", False) for item in _sdk_logger.filters):
        _sdk_logger.addFilter(_SDKLoggingFilter())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _source_failure() -> SourceError:
    return SourceError(_SAFE_FAILURE)


def _parse_date(value: object, *, end: bool = False) -> datetime:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise InputError("Dates must be ISO dates or timestamps.")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise InputError("Dates must be ISO dates or timestamps.") from None
    if result.tzinfo is None:
        result = result.replace(tzinfo=_IST)
    if end and len(value) == 10:
        result += timedelta(days=1, microseconds=-1)
    return result


def _validate_filters(filters: object) -> dict[str, Any]:
    allowed = {"query", "category", "area", "dateFrom", "dateTo", "format", "free", "sort", "limit"}
    if not isinstance(filters, dict) or set(filters) - allowed:
        raise InputError("Unsupported search filters.")
    clean = {key: copy.deepcopy(value) for key, value in filters.items() if value is not None}
    limit = clean.setdefault("limit", MAX_CANDIDATES)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_CANDIDATES:
        raise InputError("limit must be an integer from 1 to 50.")
    query = clean.get("query")
    if query is not None and (not isinstance(query, str) or not 1 <= len(query.strip()) <= 200):
        raise InputError("query must contain 1 to 200 characters.")
    for key in ("category", "area"):
        if key in clean:
            values = clean[key]
            if (
                not isinstance(values, list)
                or not 1 <= len(values) <= 40
                or any(
                    not isinstance(value, str) or not 1 <= len(value.strip()) <= 80
                    for value in values
                )
            ):
                raise InputError("Topics and areas must be bounded lists of names.")
    if "free" in clean and not isinstance(clean["free"], bool):
        raise InputError("free must be a boolean.")
    if "format" in clean and (
        not isinstance(clean["format"], str)
        or clean["format"] not in {"online", "offline", "hybrid"}
    ):
        raise InputError("format must be online, offline or hybrid.")
    if "sort" in clean and (
        not isinstance(clean["sort"], str)
        or clean["sort"] not in {"soonest", "connections", "popular", "newest", "relevance"}
    ):
        raise InputError("Unsupported sort order.")
    for key in ("dateFrom", "dateTo"):
        if key in clean:
            _parse_date(clean[key], end=key == "dateTo")
    if "dateFrom" in clean and "dateTo" in clean:
        if _parse_date(clean["dateFrom"]) > _parse_date(clean["dateTo"], end=True):
            raise InputError("dateFrom must not be after dateTo.")
    return clean


class _LimitedStream(httpx2.AsyncByteStream):
    def __init__(self, stream: httpx2.AsyncByteStream):
        self._stream = stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        received = 0
        async for chunk in self._stream:
            received += len(chunk)
            if received > MAX_RESPONSE_BYTES:
                raise _source_failure()
            yield chunk

    async def aclose(self) -> None:
        await self._stream.aclose()


class _PublicTransport(httpx2.AsyncBaseTransport):
    def __init__(self) -> None:
        self._inner = httpx2.AsyncHTTPTransport(
            trust_env=False,
            retries=0,
            limits=httpx2.Limits(max_connections=4, max_keepalive_connections=2),
        )

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        if str(request.url) != PUBLIC_ENDPOINT or request.method not in {"POST", "GET", "DELETE"}:
            raise _source_failure()
        for header in ("authorization", "cookie", "proxy-authorization"):
            request.headers.pop(header, None)
        if request.method == "POST":
            try:
                body = json.loads(request.content)
            except (ValueError, TypeError):
                raise _source_failure() from None
            method = body.get("method") if isinstance(body, dict) else None
            if method not in {
                "initialize",
                "notifications/initialized",
                "tools/list",
                "tools/call",
            }:
                raise _source_failure()
            if method == "tools/call" and body.get("params", {}).get("name") not in _PUBLIC_TOOLS:
                raise _source_failure()
        response = await self._inner.handle_async_request(request)
        if (
            response.status_code == 429
            or 300 <= response.status_code < 400
            or response.status_code >= 500
        ):
            await response.aclose()
            raise _source_failure()
        encoding = response.headers.get("content-encoding", "identity").casefold()
        if encoding != "identity":
            await response.aclose()
            raise _source_failure()
        length = response.headers.get("content-length")
        try:
            if length is not None and int(length) > MAX_RESPONSE_BYTES:
                await response.aclose()
                raise _source_failure()
        except ValueError:
            await response.aclose()
            raise _source_failure() from None
        return httpx2.Response(
            response.status_code,
            headers=response.headers,
            stream=_LimitedStream(response.stream),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()


def _structured(result: Any) -> dict[str, Any]:
    if getattr(result, "is_error", True):
        raise _source_failure()
    data = getattr(result, "structured_content", None)
    if not isinstance(data, dict):
        raise _source_failure()
    return data


def _count(value: object, *, fallback: int | None = None) -> int:
    if value is None and fallback is not None:
        return fallback
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000_000:
        raise _source_failure()
    return value


def _events(raw: object) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(raw, list) or len(raw) > MAX_CANDIDATES:
        raise _source_failure()
    result = []
    seen: set[str] = set()
    rejected = 0
    for row in raw:
        try:
            event = normalize_event(row)
        except SourceError:
            rejected += 1
            continue
        if event["id"] not in seen:
            result.append(event)
            seen.add(event["id"])
    return result, rejected


class LiveSource:
    """Only the fixed anonymous public PulseBLR endpoint is reachable."""

    data_mode = "live"

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[ClientSession]:
        logging_token = _source_logging_scope.set(True)
        try:
            with anyio.fail_after(OPERATION_TIMEOUT_SECONDS):
                async with httpx2.AsyncClient(
                    transport=_PublicTransport(),
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx2.Timeout(REQUEST_TIMEOUT_SECONDS),
                    headers={"accept-encoding": "identity"},
                ) as client:
                    async with streamable_http_client(
                        PUBLIC_ENDPOINT,
                        http_client=client,
                        max_sse_event_size=MAX_RESPONSE_BYTES,
                    ) as (read, write):
                        async with ClientSession(
                            read, write, read_timeout_seconds=REQUEST_TIMEOUT_SECONDS
                        ) as session:
                            await session.initialize()
                            yield session
        except Exception:
            raise _source_failure() from None
        finally:
            _source_logging_scope.reset(logging_token)

    async def search(self, filters: dict) -> dict:
        arguments = _validate_filters(filters)
        async with self._session() as session:
            data = _structured(await session.call_tool("search_events", arguments))
            events, rejected = _events(data.get("events"))
            if len(data["events"]) > arguments["limit"]:
                raise _source_failure()
            total = _count(data.get("totalMatching"), fallback=len(data["events"]))
            if total < len(data["events"]):
                raise _source_failure()
        warnings = list(_LIVE_WARNINGS)
        if rejected:
            warnings.append(f"Skipped {rejected} listing(s) with invalid public event fields.")
        if data.get("totalMatching") is None:
            warnings.append(
                "The public source omitted its matching total; total_matching counts returned rows only and coverage is unknown."
            )
        return {
            "events": events,
            "total_matching": total,
            "candidate_pool_truncated": total > len(data["events"])
            or bool(rejected)
            or (data.get("totalMatching") is None and len(data["events"]) == arguments["limit"]),
            "data_mode": "live",
            "fetched_at": _now_iso(),
            "warnings": warnings,
        }

    async def get_event(self, event_id: str) -> dict | None:
        if not isinstance(event_id, str) or re.fullmatch(r"[0-9a-fA-F]{24}", event_id) is None:
            raise InputError("Use a 24-character event ID returned by live search.")
        async with self._session() as session:
            result = await session.call_tool("get_event", {"id": event_id})
            prefix = f'No public PulseBLR event with id "{event_id}". Event pages are pruned '
            if (
                getattr(result, "is_error", False)
                and getattr(result, "structured_content", None) is None
                and len(getattr(result, "content", [])) == 1
                and getattr(result.content[0], "type", None) == "text"
                and result.content[0].text.startswith(prefix)
            ):
                return None
            data = _structured(result)
            if "event" in data:
                return None if data["event"] is None else normalize_event(data["event"])
            if data.get("found") is False:
                return None
            return normalize_event(data)

    async def topics(self, when: str | None = None) -> dict:
        if when is not None and (not isinstance(when, str) or when not in _NAMED_WINDOWS):
            raise InputError("Unsupported topic window.")
        async with self._session() as session:
            listing = await session.list_tools()
            if len(listing.tools) > 50 or listing.next_cursor is not None:
                raise _source_failure()
            definitions = {tool.name: tool.input_schema for tool in listing.tools}
            try:
                properties = definitions["search_events"]["properties"]
                supported_topics = _enum(properties["category"]["items"]["enum"])
                supported_areas = _enum(properties["area"]["items"]["enum"])
                maximum = definitions["trending_topics"]["properties"]["limit"]["maximum"]
            except (KeyError, TypeError):
                raise _source_failure() from None
            if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 100:
                raise _source_failure()
            arguments = {"limit": maximum}
            if when is not None:
                arguments["when"] = when
            data = _structured(await session.call_tool("trending_topics", arguments))
            observed = _observed_topics(data.get("topics"), maximum)
            total = _count(data.get("totalEvents"))
            window = data.get("window")
            if not isinstance(window, str) or window not in _NAMED_WINDOWS:
                raise _source_failure()
        warnings = list(_LIVE_WARNINGS)
        truncated = len(observed) == maximum
        if truncated:
            warnings.append(
                "Topic counts reached the public service limit; additional observed topics may be omitted."
            )
        return {
            "supported_topics": supported_topics,
            "supported_areas": supported_areas,
            "observed_topics": observed,
            "total_events": total,
            "window": window,
            "counts_truncated": truncated,
            "data_mode": "live",
            "fetched_at": _now_iso(),
            "warnings": warnings,
        }

    async def aclose(self) -> None:
        pass


def _enum(raw: object) -> list[str]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= 100:
        raise _source_failure()
    if any(not isinstance(item, str) or not 1 <= len(item) <= 80 for item in raw):
        raise _source_failure()
    return list(dict.fromkeys(raw))


def _observed_topics(raw: object, maximum: int) -> list[dict]:
    if not isinstance(raw, list) or len(raw) > maximum:
        raise _source_failure()
    observed = []
    for item in raw:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("category"), str)
            or not 1 <= len(item["category"]) <= 80
        ):
            raise _source_failure()
        entry = {"category": item["category"], "events": _count(item.get("events"))}
        share = item.get("shareOfUpcoming")
        if (
            isinstance(share, (int, float))
            and not isinstance(share, bool)
            and math.isfinite(share)
            and 0 <= share <= 1
        ):
            entry["shareOfUpcoming"] = share
        url = item.get("url")
        if isinstance(url, str) and len(url) <= 2048 and not any(ord(char) < 33 for char in url):
            try:
                parts = urlsplit(url)
            except ValueError:
                parts = None
            if parts and parts.scheme == "https" and parts.netloc == "pulseblr-u9f1.vercel.app":
                if re.fullmatch(r"/topics/[a-z0-9-]+", parts.path):
                    entry["url"] = f"https://pulseblr-u9f1.vercel.app{parts.path}"
                elif parts.path == "/" and ("category", entry["category"]) in parse_qsl(
                    parts.query
                ):
                    entry["url"] = "https://pulseblr-u9f1.vercel.app/?" + urlencode(
                        {"category": entry["category"]}
                    )
        observed.append(entry)
    return observed


class SampleSource:
    """Packaged invented events; this adapter never opens an HTTP connection."""

    data_mode = "sample"

    def __init__(self, now: datetime | None = None) -> None:
        reference = now if now is not None else datetime.now(timezone.utc)
        if (
            not isinstance(reference, datetime)
            or reference.tzinfo is None
            or reference.utcoffset() is None
        ):
            raise InputError("The sample clock must be a timezone-aware timestamp.")
        self._reference_now = reference.astimezone(_IST)
        try:
            payload = json.loads(
                files("pulseblr_events_mcp")
                .joinpath("data/sample_events.json")
                .read_text(encoding="utf-8")
            )
            self._events = [normalize_event(event) for event in payload["events"]]
            self._supported_topics = _enum(payload["supported_topics"])
            self._supported_areas = _enum(payload["supported_areas"])
        except (OSError, ValueError, KeyError, TypeError, SourceError):
            raise SourceError(
                "Packaged sample events are unavailable or invalid; reinstall this package."
            ) from None

    async def search(self, filters: dict) -> dict:
        filters = _validate_filters(filters)
        result = []
        for event in self._events:
            if "dateFrom" in filters and _parse_date(event["startsAt"]) < _parse_date(
                filters["dateFrom"]
            ):
                continue
            if "dateTo" in filters and _parse_date(event["startsAt"]) > _parse_date(
                filters["dateTo"], end=True
            ):
                continue
            if "category" in filters and not set(filters["category"]) & set(
                event.get("categories", [])
            ):
                continue
            if "area" in filters and event.get("area") not in filters["area"]:
                continue
            if "format" in filters and event.get("format") != filters["format"]:
                continue
            if "free" in filters and event.get("isFree") is not filters["free"]:
                continue
            if "query" in filters:
                haystack = " ".join(
                    str(event.get(key, ""))
                    for key in ("title", "organizer", "venue", "description", "categories")
                ).casefold()
                if not all(
                    re.search(r"\b" + re.escape(term), haystack)
                    for term in filters["query"].casefold().split()
                ):
                    continue
            result.append(event)
        sort = filters.get("sort", "connections")
        if sort == "soonest":
            result.sort(key=lambda event: (_parse_date(event["startsAt"]), event["id"]))
        elif sort == "popular":
            result.sort(key=lambda event: (-event.get("attendeeCount", 0), event["id"]))
        else:
            result.sort(
                key=lambda event: (
                    -event.get("connectionScore", 0),
                    _parse_date(event["startsAt"]),
                    event["id"],
                )
            )
        return {
            "events": copy.deepcopy(result[: filters["limit"]]),
            "total_matching": len(result),
            "candidate_pool_truncated": len(result) > filters["limit"],
            "data_mode": "sample",
            "fetched_at": _now_iso(),
            "warnings": [_SAMPLE_WARNING],
        }

    async def get_event(self, event_id: str) -> dict | None:
        if not isinstance(event_id, str) or not 1 <= len(event_id) <= 128:
            raise InputError("Use an event ID returned by sample search.")
        return next(
            (copy.deepcopy(event) for event in self._events if event["id"] == event_id), None
        )

    async def topics(self, when: str | None = None) -> dict:
        if when is not None and (not isinstance(when, str) or when not in _NAMED_WINDOWS):
            raise InputError("Unsupported topic window.")
        start = self._reference_now.replace(hour=0, minute=0, second=0, microsecond=0)
        window = when or "month"
        days = {"today": 1, "tomorrow": 1, "weekend": 2, "week": 7, "month": 31}[window]
        if window == "tomorrow":
            start += timedelta(days=1)
        elif window == "weekend":
            start += timedelta(days=-1 if start.weekday() == 6 else (5 - start.weekday()) % 7)
        end = start + timedelta(days=days)
        events = [event for event in self._events if start <= _parse_date(event["startsAt"]) < end]
        counts: dict[str, int] = {}
        for event in events:
            for category in set(event["categories"]):
                counts[category] = counts.get(category, 0) + 1
        observed = [
            {"category": category, "events": count, "shareOfUpcoming": count / len(events)}
            for category, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        return {
            "supported_topics": list(self._supported_topics),
            "supported_areas": list(self._supported_areas),
            "observed_topics": observed,
            "total_events": len(events),
            "window": window,
            "counts_truncated": False,
            "data_mode": "sample",
            "fetched_at": _now_iso(),
            "warnings": [
                _SAMPLE_WARNING,
                f"Sample topic windows use reference date {self._reference_now.date().isoformat()} IST.",
            ],
        }

    async def aclose(self) -> None:
        pass
