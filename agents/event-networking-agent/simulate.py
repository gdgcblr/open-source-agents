"""Run a whole event without real people.

Synthetic attendees join, the organiser starts rounds, rooms vote to meet in person and
the meetup agent books the configured spots. Prints how the matchmaker compares with
random grouping and whether every constraint held.

    python simulate.py                        # 250 attendees, 3 rounds, no API key needed
    python simulate.py --llm --attendees 20   # real Gemini calls (needs GEMINI_API_KEY)
"""

from __future__ import annotations

import argparse
import itertools
import logging
import random
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from networking_agent.config import load_config
from networking_agent.llm import LLM
from networking_agent.matchmaker import pair_key, random_rooms, room_quality
from networking_agent.service import EventService
from networking_agent.synthetic import make_attendees


def extraction_report(truths: dict, profiles: dict) -> str:
    """How close the profile agent got to what each synthetic attendee meant."""
    role_hits = sum(profiles[i].role == t.role for i, t in truths.items())
    tp_i = fp_i = fn_i = tp_g = fp_g = fn_g = 0
    for i, t in truths.items():
        got_i, want_i = set(profiles[i].interests), set(t.interests)
        got_g, want_g = set(profiles[i].goals), set(t.goals)
        tp_i, fp_i, fn_i = tp_i + len(got_i & want_i), fp_i + len(got_i - want_i), fn_i + len(want_i - got_i)
        tp_g, fp_g, fn_g = tp_g + len(got_g & want_g), fp_g + len(got_g - want_g), fn_g + len(want_g - got_g)
    n = len(truths)
    return (
        f"role accuracy {role_hits / n:.0%} | "
        f"interests precision {tp_i / max(tp_i + fp_i, 1):.0%} recall {tp_i / max(tp_i + fn_i, 1):.0%} | "
        f"goals precision {tp_g / max(tp_g + fp_g, 1):.0%} recall {tp_g / max(tp_g + fn_g, 1):.0%}"
    )


def peak_loads(bookings: list[tuple[str, int, datetime, datetime]]) -> dict[str, int]:
    peaks: dict[str, int] = {}
    for spot_id, _, start, _ in bookings:
        load = sum(s for sid, s, st, un in bookings if sid == spot_id and st <= start < un)
        peaks[spot_id] = max(peaks.get(spot_id, 0), load)
    return peaks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--attendees", type=int, default=250)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--meet-prob", type=float, default=0.6, help="chance each member votes to meet in person")
    ap.add_argument("--config", default="config/event.example.yaml")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--llm", action="store_true", help="call Gemini for profiles and icebreakers")
    args = ap.parse_args()

    load_dotenv()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    llm = LLM(mode="gemini" if args.llm else "offline")
    ids = itertools.count(1)
    service = EventService(cfg, llm, seed=args.seed, id_factory=lambda: f"a{next(ids):04d}")
    rng = random.Random(args.seed)

    print(f"Event: {cfg.name}")
    print(f"Spots: {', '.join(f'{s.name} ({s.capacity})' for s in cfg.spots)}")
    print(f"LLM:   {'Gemini ' + llm.model if llm.enabled else 'offline (keyword rules + templates)'}\n")

    # --- join ---------------------------------------------------------------------
    synthetic = make_attendees(args.attendees, seed=args.seed)
    t0 = time.perf_counter()
    # Offline joins are instant; keep them sequential so ids, and therefore results, are reproducible.
    with ThreadPoolExecutor(max_workers=8 if llm.enabled else 1) as pool:
        joined = list(pool.map(lambda s: service.join(s.nickname, s.about)[1], synthetic))
    truths = {a.id: s.truth for a, s in zip(joined, synthetic)}
    print(f"{len(joined)} attendees joined in {time.perf_counter() - t0:.1f}s")
    print(f"Profile agent vs ground truth: {extraction_report(truths, {a.id: a.profile for a in joined})}\n")

    profiles = {a.id: a.profile for a in joined}
    now = datetime(2026, 10, 24, 11, 0, tzinfo=timezone.utc)
    bookings, waits, unplaced = [], [], 0
    random_met: set[frozenset[str]] = set()
    random_repeats = 0

    for r in range(1, args.rounds + 1):
        t0 = time.perf_counter()
        rooms = service.start_round()
        took = time.perf_counter() - t0
        groups = [room.member_ids for room in rooms]

        baseline = random_rooms(list(profiles), cfg.room_size, seed=args.seed + r)
        for g in baseline:
            pairs = {pair_key(a, b) for i, a in enumerate(g) for b in g[i + 1 :]}
            random_repeats += len(pairs & random_met)
            random_met |= pairs

        mm, rnd = room_quality(groups, profiles), room_quality(baseline, profiles)
        sizes = sorted({len(g) for g in groups})
        print(f"Round {r}: {len(rooms)} rooms (sizes {sizes}) in {took:.2f}s")
        print(f"  {'':28} {'matchmaker':>10} {'random':>8}")
        for key, label in [
            ("mean_pair_affinity", "mean pair affinity"),
            ("share_with_common_interest", "share w/ common interest"),
            ("share_with_goal_match", "share w/ goal match"),
        ]:
            fmt = "{:>10.2f} {:>8.2f}" if key == "mean_pair_affinity" else "{:>10.0%} {:>8.0%}"
            print(f"  {label:28} " + fmt.format(mm[key], rnd[key]))

        meetups = 0
        for room in rooms:
            for member in room.member_ids:
                if rng.random() < args.meet_prob:
                    service.vote_meet(member, now=now)
            if len(room.votes) >= service.votes_needed(room):
                if room.meetup:
                    meetups += 1
                    m = room.meetup
                    bookings.append((m.spot_id, len(room.member_ids), m.meet_at, m.until))
                    waits.append((m.meet_at - now - timedelta(minutes=cfg.walk_minutes)).total_seconds() / 60)
                else:
                    unplaced += 1
        print(f"  {meetups} rooms chose to meet in person\n")
        now += timedelta(minutes=cfg.walk_minutes + cfg.meetup_minutes + 2)

    # --- constraints ----------------------------------------------------------------
    seen: set[frozenset[str]] = set()
    repeats = 0
    for room in service.rooms.values():
        pairs = {pair_key(a, b) for i, a in enumerate(room.member_ids) for b in room.member_ids[i + 1 :]}
        repeats += len(pairs & seen)
        seen |= pairs
    caps = {s.id: s.capacity for s in cfg.spots}
    peaks = peak_loads(bookings)
    print("Constraints")
    print(f"  repeat pairings across rounds: {repeats} (random grouping: {random_repeats})")
    print(f"  spot peak load vs capacity:    " + ", ".join(f"{k} {peaks.get(k, 0)}/{c}" for k, c in caps.items()))
    print(f"  capacity ever exceeded:        {any(peaks.get(k, 0) > c for k, c in caps.items())}")
    if waits:
        print(f"  wait for a free spot (min):    median {statistics.median(waits):.0f}, max {max(waits):.0f}")
    print(f"  rooms that found no spot within {cfg.max_wait_minutes} min: {unplaced}")

    sample = next(iter(service.rooms.values()))
    print(f"\nSample room {sample.id}:")
    for m in sample.member_ids:
        a = service.attendees[m]
        print(f"  - {a.nickname} ({a.profile.role.value}; {', '.join(a.profile.interests)}): {a.profile.one_liner}")
    print(f"  why:        {sample.why}")
    print(f"  icebreaker: {sample.icebreaker}")
    if sample.meetup:
        print(f"  meetup:     {sample.meetup.spot_name} at {sample.meetup.meet_at:%H:%M}")
    if llm.enabled:
        print(f"\nGemini calls: {llm.calls}, failures (fell back to offline): {llm.failures}")


if __name__ == "__main__":
    main()
