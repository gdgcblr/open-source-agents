"""Provider-neutral orchestration of the five public MCP capabilities."""

import asyncio
from datetime import datetime, timezone

from .discovery import _clock, filter_events, recommend_communities, resolve_window
from .errors import InputError, SourceError
from .models import EVENT_ID, normalize_event
from .planner import plan_schedule


def _strings(value, name, maximum=20):
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > maximum:
        raise InputError(f"{name} must contain at most {maximum} strings.")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 100 for item in value):
        raise InputError(f"{name} must contain non-empty strings of at most 100 characters.")
    return list(dict.fromkeys(item.strip() for item in value))


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise InputError(f"{name} must be an integer between {low} and {high}.")
    return value


class EventTools:
    def __init__(self, source, now=None):
        self.source = source
        self.now = now
        if source.data_mode not in {"live", "sample"}:
            raise InputError("Choose an explicit live or sample source.")
        if now is not None:
            if source.data_mode != "sample":
                raise InputError("A fixed clock is permitted only in sample mode.")
            resolve_window(now=now)

    async def _call(self, method, *args):
        try:
            return await getattr(self.source, method)(*args)
        except (InputError, SourceError):
            raise
        except Exception:
            raise SourceError(
                "The public event source could not complete this request. "
                "Retry later or explicitly select sample mode."
            ) from None

    def _meta(self, payload=None):
        payload = payload or {}
        warnings = list(payload.get("warnings", []))
        if self.source.data_mode == "sample":
            notice = (
                "Fictional sample data with fixed dates and example.com links; not real listings."
            )
            if notice not in warnings:
                warnings.insert(0, notice)
        else:
            warnings.extend(
                [
                    "Listing freshness and registration availability are not independently verified.",
                    "Free means listed free by PulseBLR; the upstream service may default unknown cost to free.",
                ]
            )
        return {
            "data_mode": self.source.data_mode,
            "fetched_at": payload.get("fetched_at", datetime.now(timezone.utc).isoformat()),
            "warnings": list(dict.fromkeys(warnings)),
        }

    def _filters(
        self,
        query=None,
        topics=None,
        areas=None,
        when=None,
        date_from=None,
        date_to=None,
        format=None,
        free_only=None,
        limit=50,
    ):
        _integer(limit, "limit", 1, 50)
        if query is not None and (
            not isinstance(query, str) or not query.strip() or len(query) > 200
        ):
            raise InputError("query must be a non-empty string of at most 200 characters.")
        topics = _strings(topics, "topics")
        areas = _strings(areas, "areas")
        if format is not None and format not in {"online", "offline", "hybrid"}:
            raise InputError("format must be online, offline or hybrid.")
        if free_only is not None and type(free_only) is not bool:
            raise InputError("free_only must be a boolean.")
        start, end = resolve_window(when, date_from, date_to, self.now)
        start = max(start, _clock(self.now))
        values = {
            "query": query,
            "category": topics,
            "area": areas,
            "dateFrom": start.isoformat(),
            "dateTo": end.isoformat(),
            "format": format,
            "free": free_only,
            "sort": "relevance" if query else "soonest",
            "limit": limit,
        }
        return {key: value for key, value in values.items() if value is not None}

    async def _discover(self, filters):
        if datetime.fromisoformat(filters["dateFrom"]) >= datetime.fromisoformat(filters["dateTo"]):
            return {
                **self._meta(),
                "events": [],
                "total_matching": 0,
                "candidate_pool_truncated": False,
            }
        batch = await self._call("search", filters)
        events = [normalize_event(event) for event in batch["events"]]
        # The upstream end is inclusive; local filtering owns the half-open boundary.
        events = filter_events(events, filters, self.now)
        return {**batch, "events": events}

    async def _candidates(self, event_ids, discovery):
        if event_ids is None:
            filters = self._filters(**discovery, limit=50)
            batch = await self._discover(filters)
            return batch["events"], {
                **self._meta(batch),
                "total_matching": batch.get("total_matching"),
                "candidate_pool_truncated": bool(batch.get("candidate_pool_truncated")),
                "fetched_count": len(batch["events"]),
            }
        if any(value is not None for value in discovery.values()):
            raise InputError(
                "Use event_ids or discovery filters, not both. interests may rank either."
            )
        if not isinstance(event_ids, list) or not 1 <= len(event_ids) <= 10:
            raise InputError("event_ids must contain between 1 and 10 public event IDs.")
        if any(not isinstance(item, str) or not EVENT_ID.fullmatch(item) for item in event_ids):
            raise InputError("event_ids must contain public IDs, not URLs or paths.")
        ids = list(dict.fromkeys(event_ids))
        semaphore = asyncio.Semaphore(3)

        async def get(event_id):
            async with semaphore:
                result = await self._call("get_event", event_id)
                return normalize_event(result) if result is not None else None

        resolved = await asyncio.gather(*(get(event_id) for event_id in ids))
        missing = [event_id for event_id, event in zip(ids, resolved) if event is None]
        meta = self._meta()
        if missing:
            meta["warnings"].append(
                "Some requested IDs are missing or expired; no replacements were added."
            )
        events = [event for event in resolved if event is not None]
        return events, {
            **meta,
            "requested_count": len(ids),
            "resolved_count": len(events),
            "missing_event_ids": missing,
            "candidate_pool_truncated": False,
        }

    async def search_events(
        self,
        query=None,
        topics=None,
        areas=None,
        when=None,
        date_from=None,
        date_to=None,
        format=None,
        free_only=None,
        limit=10,
    ):
        filters = self._filters(
            query, topics, areas, when, date_from, date_to, format, free_only, limit
        )
        batch = await self._discover(filters)
        events = []
        for event in batch["events"]:
            reasons = ["Starts within the requested IST window and has not already started."]
            for value, label in (
                (query, "Query"),
                (topics, "Topics"),
                (areas, "Areas"),
                (format, "Format"),
                (free_only, "Listed-free filter"),
            ):
                if value is not None:
                    reasons.append(f"{label}: {value}")
            events.append({**event, "why_matched": reasons})
        return {
            **self._meta(batch),
            "events": events,
            "returned": len(events),
            "total_matching": batch.get("total_matching"),
            "candidate_pool_truncated": bool(batch.get("candidate_pool_truncated")),
            "filters": filters,
        }

    async def get_event(self, event_id):
        if not isinstance(event_id, str) or not EVENT_ID.fullmatch(event_id):
            raise InputError(
                "event_id must be a public event ID returned by search, not a URL or path."
            )
        event = await self._call("get_event", event_id)
        return {
            **self._meta(),
            "event": normalize_event(event) if event is not None else None,
            "found": event is not None,
        }

    async def list_topics(self, when=None):
        if when is not None and when not in {"today", "tomorrow", "weekend", "week", "month"}:
            raise InputError("Topic counts support today, tomorrow, weekend, week or month.")
        result = await self._call("topics", when)
        return {**result, **self._meta(result)}

    async def recommend_communities(
        self,
        interests=None,
        event_ids=None,
        query=None,
        topics=None,
        areas=None,
        when=None,
        date_from=None,
        date_to=None,
        format=None,
        free_only=None,
        limit=5,
    ):
        interests = _strings(interests, "interests")
        _integer(limit, "limit", 1, 10)
        discovery = dict(
            query=query,
            topics=topics,
            areas=areas,
            when=when,
            date_from=date_from,
            date_to=date_to,
            format=format,
            free_only=free_only,
        )
        events, meta = await self._candidates(event_ids, discovery)
        events = filter_events(events, {}, self.now)
        result = recommend_communities(events, interests=interests, limit=limit)
        warnings = list(dict.fromkeys(meta["warnings"] + result.get("warnings", [])))
        return {
            **result,
            **meta,
            "warnings": warnings,
            "scope": "Organisers observed in the selected events, not a membership directory.",
        }

    async def plan_schedule(
        self,
        interests=None,
        event_ids=None,
        query=None,
        topics=None,
        areas=None,
        when=None,
        date_from=None,
        date_to=None,
        format=None,
        free_only=None,
        max_events=2,
        transfer_buffer_minutes=60,
        duration_policy="strict",
        assumed_duration_minutes=None,
    ):
        interests = _strings(interests, "interests")
        _integer(max_events, "max_events", 1, 3)
        _integer(transfer_buffer_minutes, "transfer_buffer_minutes", 0, 240)
        if duration_policy not in {"strict", "estimate"}:
            raise InputError("duration_policy must be strict or estimate.")
        if duration_policy == "estimate":
            _integer(assumed_duration_minutes, "assumed_duration_minutes", 1, 1440)
        elif assumed_duration_minutes is not None:
            raise InputError("An assumed duration requires duration_policy='estimate'.")
        discovery = dict(
            query=query,
            topics=topics,
            areas=areas,
            when=when,
            date_from=date_from,
            date_to=date_to,
            format=format,
            free_only=free_only,
        )
        events, meta = await self._candidates(event_ids, discovery)
        result = plan_schedule(
            events,
            interests=interests,
            max_events=max_events,
            transfer_buffer_minutes=transfer_buffer_minutes,
            duration_policy=duration_policy,
            assumed_duration_minutes=assumed_duration_minutes,
            now=self.now,
        )
        warnings = list(dict.fromkeys(meta["warnings"] + result.get("warnings", [])))
        return {**result, **meta, "warnings": warnings}
