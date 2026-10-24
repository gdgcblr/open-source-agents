"""HTTP API the virtual-world UI (or any client) talks to.

Attendees authenticate with the secret token they get from /api/join, sent as the
X-Attendee-Token header. Organiser endpoints need the X-Admin-Token header.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import load_config
from .models import Attendee, Goal, Meetup, Role, Room, Spot
from .service import EventError, EventService

log = logging.getLogger(__name__)
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class JoinRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=24)
    about: str = Field(default="", max_length=1000, description="What you do and who you'd like to meet")
    contact: str | None = Field(default=None, max_length=120, description="Shared only on a mutual connect")


class PublicProfile(BaseModel):
    id: str
    nickname: str
    role: Role
    interests: list[str]
    goals: list[Goal]
    one_liner: str

    @classmethod
    def of(cls, a: Attendee) -> PublicProfile:
        p = a.profile
        return cls(id=a.id, nickname=a.nickname, role=p.role, interests=p.interests, goals=p.goals, one_liner=p.one_liner)


class JoinResponse(BaseModel):
    token: str
    me: PublicProfile


class RoomView(BaseModel):
    id: str
    round: int
    members: list[PublicProfile]
    shared_interests: list[str]
    why: str
    icebreaker: str
    votes: int
    votes_needed: int
    i_voted: bool
    meetup: Meetup | None
    liked_ids: list[str] = Field(default_factory=list)
    mutual_ids: list[str] = Field(default_factory=list)


class FloorRoom(BaseModel):
    id: str
    round: int
    member_ids: list[str]
    shared_interests: list[str]
    why: str
    icebreaker: str
    votes: int
    votes_needed: int
    meetup: Meetup | None


class SeedRequest(BaseModel):
    count: int = Field(default=15, ge=1, le=100)
    use_llm: bool = False


class SimulateRequest(BaseModel):
    meet_prob: float = Field(default=0.65, ge=0.0, le=1.0)
    like_prob: float = Field(default=0.75, ge=0.0, le=1.0)


class LikeRequest(BaseModel):
    to_id: str


class Connection(BaseModel):
    nickname: str
    contact: str | None


def create_app(service: EventService | None = None, admin_token: str | None = None) -> FastAPI:
    if service is None:
        load_dotenv()
        service = EventService(load_config(os.getenv("EVENT_CONFIG", "config/event.example.yaml")))
    admin_token = admin_token or os.getenv("ADMIN_TOKEN")
    if not admin_token:
        admin_token = secrets.token_urlsafe(12)
        log.warning("ADMIN_TOKEN not set; generated one for this run: %s", admin_token)

    app = FastAPI(title="Event Networking Agent", version="0.1.0")
    app.state.service = service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def attendee(x_attendee_token: str = Header()) -> Attendee:
        try:
            return service.whoami(x_attendee_token)
        except EventError as exc:
            raise HTTPException(401, str(exc)) from exc

    def admin(x_admin_token: str = Header()) -> None:
        if not secrets.compare_digest(x_admin_token, admin_token):
            raise HTTPException(403, "bad admin token")

    def view(room: Room, me: Attendee) -> RoomView:
        liked = [m for m in room.member_ids if (me.id, m) in service.likes]
        mutual = [m for m in liked if (m, me.id) in service.likes]
        return RoomView(
            id=room.id,
            round=room.round,
            members=[PublicProfile.of(service.attendees[m]) for m in room.member_ids],
            shared_interests=room.shared_interests,
            why=room.why,
            icebreaker=room.icebreaker,
            votes=len(room.votes),
            votes_needed=service.votes_needed(room),
            i_voted=me.id in room.votes,
            meetup=room.meetup,
            liked_ids=liked,
            mutual_ids=mutual,
        )

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/event")
    def event() -> dict:
        cfg = service.config
        return {"name": cfg.name, "room_size": cfg.room_size, "round": service.round, "spots": cfg.spots}

    @app.post("/api/join", response_model=JoinResponse)
    def join(req: JoinRequest) -> JoinResponse:
        try:
            token, a = service.join(req.nickname, req.about, req.contact)
        except EventError as exc:
            raise HTTPException(400, str(exc)) from exc
        return JoinResponse(token=token, me=PublicProfile.of(a))

    @app.get("/api/me", response_model=PublicProfile)
    def me(a: Attendee = Depends(attendee)) -> PublicProfile:
        return PublicProfile.of(a)

    @app.get("/api/me/room", response_model=RoomView | None)
    def my_room(a: Attendee = Depends(attendee)) -> RoomView | None:
        room = service.room_of(a.id)
        return view(room, a) if room else None

    @app.post("/api/me/room/meet", response_model=RoomView)
    def meet(a: Attendee = Depends(attendee)) -> RoomView:
        try:
            return view(service.vote_meet(a.id), a)
        except EventError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/me/like")
    def like(req: LikeRequest, a: Attendee = Depends(attendee)) -> dict:
        try:
            return {"mutual": service.like(a.id, req.to_id)}
        except EventError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/me/connections", response_model=list[Connection])
    def connections(a: Attendee = Depends(attendee)) -> list[Connection]:
        return [Connection(nickname=c.nickname, contact=c.contact) for c in service.connections(a.id)]

    @app.post("/api/admin/rounds", dependencies=[Depends(admin)])
    def start_round() -> dict:
        rooms = service.start_round()
        return {"round": service.round, "rooms": len(rooms)}

    @app.get("/api/admin/stats", dependencies=[Depends(admin)])
    def stats() -> dict:
        return service.stats()

    @app.get("/api/spots", response_model=list[Spot])
    def spots() -> list[Spot]:
        return service.config.spots

    @app.get("/api/world")
    def world() -> dict:
        cfg = service.config
        rooms = [
            FloorRoom(
                id=r.id,
                round=r.round,
                member_ids=r.member_ids,
                shared_interests=r.shared_interests,
                why=r.why,
                icebreaker=r.icebreaker,
                votes=len(r.votes),
                votes_needed=service.votes_needed(r),
                meetup=r.meetup,
            )
            for r in service.current_rooms()
        ]
        attendees = [PublicProfile.of(a) for a in service.attendees.values()]
        return {
            "name": cfg.name,
            "room_size": cfg.room_size,
            "walk_minutes": cfg.walk_minutes,
            "meetup_minutes": cfg.meetup_minutes,
            "round": service.round,
            "spots": cfg.spots,
            "attendees": attendees,
            "synthetic_ids": sorted(service.synthetic_ids),
            "rooms": rooms,
            "stats": service.stats(),
        }

    @app.post("/api/demo/seed")
    def demo_seed(req: SeedRequest = SeedRequest()) -> dict:
        added = service.seed_synthetic(req.count, use_llm=req.use_llm)
        return {"added": len(added), "attendees": len(service.attendees)}

    @app.post("/api/demo/round")
    def demo_round() -> dict:
        rooms = service.start_round()
        return {"round": service.round, "rooms": len(rooms)}

    @app.post("/api/demo/simulate")
    def demo_simulate(req: SimulateRequest = SimulateRequest()) -> dict:
        return service.simulate_activity(meet_prob=req.meet_prob, like_prob=req.like_prob)

    @app.post("/api/demo/reset")
    def demo_reset() -> dict:
        service.reset()
        return {"ok": True}

    if WEB_DIR.is_dir():
        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

        app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")

    return app
