"""Event service: the in-memory state of one event, and the loop the agents run in.

join -> profile agent -> (organiser starts a round) -> matchmaker -> host agent per room
-> members vote to meet in person -> meetup agent books a spot -> feedback -> next round.
"""

from __future__ import annotations

import math
import random
import secrets
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .config import EventConfig
from .host_agent import HostAgent, intro_offline, shared_interests
from .llm import LLM
from .matchmaker import Matchmaker, pair_key
from .meetup_agent import MeetupPlanner
from .models import Attendee, Room
from .profile_agent import ProfileAgent, extract_offline
from .synthetic import make_attendee

MAX_NICKNAME = 24
MAX_ABOUT = 1000


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventError(Exception):
    """A request that is understood but not allowed (unknown id, not your room, ...)."""


class EventService:
    def __init__(
        self,
        config: EventConfig,
        llm: LLM | None = None,
        seed: int = 0,
        intro_workers: int = 8,
        id_factory: Callable[[], str] | None = None,  # the simulator passes a counter for reproducible runs
    ):
        self.config = config
        self.new_id = id_factory or (lambda: secrets.token_hex(4))
        self.llm = llm or LLM()
        self.seed = seed
        self.intro_workers = intro_workers
        self.profile_agent = ProfileAgent(self.llm)
        self.host_agent = HostAgent(self.llm)
        self.planner = MeetupPlanner(config.spots, config.walk_minutes, config.meetup_minutes, config.max_wait_minutes)

        self._lock = threading.RLock()
        self._round_lock = threading.Lock()
        self.attendees: dict[str, Attendee] = {}
        self._tokens: dict[str, str] = {}  # secret token -> public attendee id
        self.synthetic_ids: set[str] = set()
        self.rooms: dict[str, Room] = {}
        self.current_room: dict[str, str] = {}  # attendee id -> room id for the current round
        self.round = 0
        self.met: set[frozenset[str]] = set()
        self.likes: set[tuple[str, str]] = set()

    # --- attendees -------------------------------------------------------------------

    def join(self, nickname: str, about: str, contact: str | None = None) -> tuple[str, Attendee]:
        """Returns (secret token, attendee). The token is the attendee's only credential."""
        nickname = " ".join(nickname.split())[:MAX_NICKNAME]
        if not nickname:
            raise EventError("nickname is required")
        about = about.strip()[:MAX_ABOUT]
        profile = self.profile_agent.build(about)  # slow LLM call; keep it outside the lock
        with self._lock:
            attendee = Attendee(
                id=self.new_id(),
                nickname=nickname,
                about=about,
                profile=profile,
                contact=(contact or "").strip() or None,
            )
            token = secrets.token_urlsafe(16)
            self.attendees[attendee.id] = attendee
            self._tokens[token] = attendee.id
            return token, attendee

    def whoami(self, token: str) -> Attendee:
        with self._lock:
            attendee_id = self._tokens.get(token)
            if attendee_id is None:
                raise EventError("unknown token")
            return self.attendees[attendee_id]

    # --- rounds ----------------------------------------------------------------------

    def start_round(self) -> list[Room]:
        """Regroup everyone who has joined. Rooms from the previous round are closed."""
        with self._round_lock:
            with self._lock:
                profiles = {a.id: a.profile for a in self.attendees.values()}
                met = set(self.met)
                round_no = self.round + 1
            groups = Matchmaker(self.config.room_size, seed=self.seed + round_no).group(profiles, met)

            with self._lock:
                members = [[self.attendees[i] for i in g] for g in groups]
            # Introductions may call the LLM once per room; run them concurrently.
            with ThreadPoolExecutor(max_workers=self.intro_workers) as pool:
                intros = list(pool.map(lambda ms: self.host_agent.introduce(ms, seed=self.seed + round_no), members))

            rooms = [
                Room(
                    id=f"r{round_no}-{k + 1}",
                    round=round_no,
                    member_ids=[m.id for m in ms],
                    shared_interests=shared_interests(ms),
                    why=intro.why,
                    icebreaker=intro.icebreaker,
                )
                for k, (ms, intro) in enumerate(zip(members, intros))
            ]
            with self._lock:
                self.round = round_no
                self.current_room = {}
                for room in rooms:
                    self.rooms[room.id] = room
                    for a in room.member_ids:
                        self.current_room[a] = room.id
                    for a, b in ((a, b) for i, a in enumerate(room.member_ids) for b in room.member_ids[i + 1 :]):
                        self.met.add(pair_key(a, b))
            return rooms

    def room_of(self, attendee_id: str) -> Room | None:
        with self._lock:
            room_id = self.current_room.get(attendee_id)
            return self.rooms[room_id] if room_id else None

    # --- meeting in person -----------------------------------------------------------

    def votes_needed(self, room: Room) -> int:
        return math.ceil(len(room.member_ids) / 2)

    def vote_meet(self, attendee_id: str, now: datetime | None = None) -> Room:
        """Record that this attendee wants to meet their room in person. Once half the
        room agrees, the meetup agent books a spot."""
        with self._lock:
            room = self.room_of(attendee_id)
            if room is None:
                raise EventError("you are not in a room yet; wait for the next round")
            if attendee_id not in room.votes:
                room.votes.append(attendee_id)
            if room.meetup is None and len(room.votes) >= self.votes_needed(room):
                room.meetup = self.planner.plan(len(room.member_ids), now or utcnow())
            return room

    # --- staying in touch ------------------------------------------------------------

    def like(self, from_id: str, to_id: str) -> bool:
        """'I'd like to stay in touch.' Returns True when the like is mutual."""
        with self._lock:
            if to_id not in self.attendees or from_id == to_id:
                raise EventError("unknown attendee")
            if pair_key(from_id, to_id) not in self.met:
                raise EventError("you can only connect with people you have shared a room with")
            self.likes.add((from_id, to_id))
            return (to_id, from_id) in self.likes

    def connections(self, attendee_id: str) -> list[Attendee]:
        """People who liked this attendee back. Contacts are only shared on a mutual like."""
        with self._lock:
            return [
                self.attendees[b]
                for (a, b) in self.likes
                if a == attendee_id and (b, a) in self.likes
            ]

    def stats(self) -> dict:
        with self._lock:
            current = [r for r in self.rooms.values() if r.round == self.round]
            return {
                "attendees": len(self.attendees),
                "round": self.round,
                "rooms_this_round": len(current),
                "meetups_this_round": sum(r.meetup is not None for r in current),
                "mutual_connections": sum(1 for (a, b) in self.likes if (b, a) in self.likes) // 2,
                "llm": {"enabled": self.llm.enabled, "calls": self.llm.calls, "failures": self.llm.failures},
            }

    def current_rooms(self) -> list[Room]:
        with self._lock:
            return [r for r in self.rooms.values() if r.round == self.round]

    # --- live demo / simulator helpers for the virtual-world UI ----------------------

    def seed_synthetic(self, count: int = 15, use_llm: bool = False) -> list[Attendee]:
        """Add synthetic attendees so a single user or organiser can see a lively venue floor."""
        count = max(1, min(count, 100))
        with self._lock:
            base_idx = len(self.attendees) + 1
            rng = random.Random(self.seed + base_idx * 31)
        synth_list = [make_attendee(rng, base_idx + i) for i in range(count)]

        created: list[Attendee] = []
        for s in synth_list:
            contact = f"@{s.nickname.replace('-', '_')}"
            if use_llm:
                _, a = self.join(s.nickname, s.about, contact)
                with self._lock:
                    self.synthetic_ids.add(a.id)
                created.append(a)
            else:
                profile = extract_offline(s.about)
                with self._lock:
                    a = Attendee(
                        id=self.new_id(),
                        nickname=s.nickname,
                        about=s.about,
                        profile=profile,
                        contact=contact,
                    )
                    token = secrets.token_urlsafe(16)
                    self.attendees[a.id] = a
                    self._tokens[token] = a.id
                    self.synthetic_ids.add(a.id)
                    created.append(a)
        return created

    def simulate_activity(
        self,
        meet_prob: float = 0.65,
        like_prob: float = 0.7,
        now: datetime | None = None,
    ) -> dict:
        """Let synthetic attendees in active rooms vote to meet in person and connect."""
        with self._lock:
            current = [r for r in self.rooms.values() if r.round == self.round]
            rng = random.Random(self.seed + self.round * 97 + len(self.likes) + sum(len(r.votes) for r in current))
            votes_cast = 0
            likes_cast = 0
            ts = now or utcnow()

            for room in current:
                bots = [m for m in room.member_ids if m in self.synthetic_ids]
                humans = [m for m in room.member_ids if m not in self.synthetic_ids]
                voters = bots if bots else room.member_ids

                for m in voters:
                    if m not in room.votes and rng.random() < meet_prob:
                        self.vote_meet(m, now=ts)
                        votes_cast += 1

                # If a human is in this room and bots are present, ensure enough bots vote
                # so the human can experience the in-person spot booking flow on the map.
                if humans and bots and room.meetup is None:
                    for m in bots:
                        if len(room.votes) >= self.votes_needed(room):
                            break
                        if m not in room.votes:
                            self.vote_meet(m, now=ts)
                            votes_cast += 1

                for b in bots:
                    for target in room.member_ids:
                        if b == target:
                            continue
                        # Bots always reciprocate a human's like, or initiate with like_prob.
                        chance = 0.95 if (target, b) in self.likes or target in humans else like_prob
                        if (b, target) not in self.likes and rng.random() < chance:
                            self.like(b, target)
                            likes_cast += 1

            meetups = sum(r.meetup is not None for r in current)
            return {"votes_cast": votes_cast, "likes_cast": likes_cast, "meetups_this_round": meetups}

    def reset(self) -> None:
        """Reset all in-memory state for a fresh event run."""
        with self._round_lock:
            with self._lock:
                self.attendees.clear()
                self._tokens.clear()
                self.synthetic_ids.clear()
                self.rooms.clear()
                self.current_room.clear()
                self.round = 0
                self.met.clear()
                self.likes.clear()
                self.planner.reservations.clear()
