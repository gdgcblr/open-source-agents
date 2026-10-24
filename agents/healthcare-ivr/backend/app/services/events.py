"""Call timeline events, and the live feed that streams call updates to the dashboard."""

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CallEvent, CallEventType


class LiveFeed:
    """Publish/subscribe for live call updates inside one backend process.

    The bridge publishes transcript turns, events and what the receptionist is doing; the
    dashboard subscribes over server-sent events. Running several backend instances would need
    a shared broker such as Redis instead, alongside a shared database.
    """

    def __init__(self, queue_size: int = 100) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._queue_size = queue_size

    def publish(self, call_id: str, message: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(call_id, ())):
            # A stalled viewer misses this update; its next refetch catches up.
            with suppress(asyncio.QueueFull):
                queue.put_nowait(message)

    @asynccontextmanager
    async def subscribe(self, call_id: str) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers[call_id].add(queue)
        try:
            yield queue
        finally:
            self._subscribers[call_id].discard(queue)
            if not self._subscribers[call_id]:
                del self._subscribers[call_id]


async def record_event(
    db: AsyncSession,
    call_id: str,
    event_type: CallEventType,
    message: str,
    *,
    data: dict[str, Any] | None = None,
    feed: LiveFeed | None = None,
) -> None:
    """Save an event on the call's timeline and tell anyone watching the call live."""
    db.add(CallEvent(call_id=call_id, type=event_type, message=message, data=data))
    await db.commit()
    if feed is not None:
        feed.publish(call_id, {"kind": "event", "type": event_type.value, "message": message})
