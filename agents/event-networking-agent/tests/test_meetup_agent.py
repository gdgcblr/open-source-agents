from datetime import datetime, timedelta, timezone

from networking_agent.meetup_agent import MeetupPlanner
from networking_agent.models import Spot

NOW = datetime(2026, 10, 24, 11, 0, tzinfo=timezone.utc)


def planner(*capacities, max_wait=30):
    spots = [Spot(id=f"s{i}", name=f"Spot {i}", capacity=c) for i, c in enumerate(capacities)]
    return MeetupPlanner(spots, walk_minutes=3, meetup_minutes=10, max_wait_minutes=max_wait)


def test_first_group_goes_now_plus_walk():
    m = planner(10).plan(5, NOW)
    assert m.meet_at == NOW + timedelta(minutes=3)
    assert m.until == m.meet_at + timedelta(minutes=10)


def test_full_spot_gives_the_next_free_slot():
    p = planner(10)
    a, b, c = (p.plan(5, NOW) for _ in range(3))
    assert a.meet_at == b.meet_at
    assert c.meet_at == a.until  # had to wait for the first two to leave


def test_prefers_the_emptier_spot_at_the_same_time():
    p = planner(10, 20)
    first = p.plan(5, NOW)
    second = p.plan(5, NOW)
    assert first.meet_at == second.meet_at
    assert {first.spot_id, second.spot_id} == {"s0", "s1"}


def test_capacity_never_exceeded():
    p = planner(15, 10, 25)
    bookings = [p.plan(5, NOW + timedelta(minutes=i % 7)) for i in range(60)]
    bookings = [b for b in bookings if b]
    for b in bookings:
        load = sum(5 for o in bookings if o.spot_id == b.spot_id and o.meet_at <= b.meet_at < o.until)
        cap = {"s0": 15, "s1": 10, "s2": 25}[b.spot_id]
        assert load <= cap


def test_gives_up_beyond_max_wait():
    p = planner(5, max_wait=0)
    assert p.plan(5, NOW) is not None
    assert p.plan(5, NOW) is None


def test_expired_bookings_free_the_spot():
    p = planner(5)
    p.plan(5, NOW)
    later = p.plan(5, NOW + timedelta(minutes=30))
    assert later.meet_at == NOW + timedelta(minutes=33)


def test_group_bigger_than_every_spot():
    assert planner(4).plan(5, NOW) is None
