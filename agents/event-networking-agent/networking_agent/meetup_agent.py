"""Meetup agent: books a physical spot for a room that chose to meet in person.

Spots have a capacity, so when everything nearby is busy the group gets the earliest slot
that frees up instead of a flat "no".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import Meetup, Spot


@dataclass
class Reservation:
    spot_id: str
    size: int
    start: datetime
    until: datetime


class MeetupPlanner:
    def __init__(self, spots: list[Spot], walk_minutes: int = 3, meetup_minutes: int = 10, max_wait_minutes: int = 30):
        self.spots = spots
        self.walk = timedelta(minutes=walk_minutes)
        self.hold = timedelta(minutes=meetup_minutes)
        self.max_wait = timedelta(minutes=max_wait_minutes)
        self.reservations: list[Reservation] = []

    def peak_load(self, spot_id: str, start: datetime, end: datetime) -> int:
        """Most people booked at `spot_id` at any moment in [start, end)."""
        overlapping = [r for r in self.reservations if r.spot_id == spot_id and r.start < end and r.until > start]
        # Load only rises at a reservation's start, so checking those instants is enough.
        instants = [start] + [r.start for r in overlapping if r.start > start]
        return max((sum(r.size for r in overlapping if r.start <= t < r.until) for t in instants), default=0)

    def plan(self, size: int, now: datetime) -> Meetup | None:
        """Earliest (then least crowded) spot that fits `size` people, or None if nothing
        frees up within max_wait."""
        self.reservations = [r for r in self.reservations if r.until > now]
        earliest = now + self.walk
        best = None  # ((start, crowding, spot id), spot)
        for spot in self.spots:
            if spot.capacity < size:
                continue
            # A spot can only become free when an existing booking there ends.
            starts = sorted({earliest} | {r.until for r in self.reservations if r.spot_id == spot.id and r.until > earliest})
            for start in starts:
                if start - earliest > self.max_wait:
                    break
                load = self.peak_load(spot.id, start, start + self.hold)
                if load + size <= spot.capacity:
                    key = (start, load / spot.capacity, spot.id)
                    if best is None or key < best[0]:
                        best = (key, spot)
                    break
        if best is None:
            return None
        (start, _, _), spot = best
        self.reservations.append(Reservation(spot.id, size, start, start + self.hold))
        return Meetup(
            spot_id=spot.id,
            spot_name=spot.name,
            spot_description=spot.description,
            meet_at=start,
            until=start + self.hold,
        )
