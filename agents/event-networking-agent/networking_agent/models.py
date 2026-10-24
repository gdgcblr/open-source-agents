"""Data models shared by the agents, the event service and the API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

# Interests are normalised to this fixed vocabulary so the matchmaker can compare
# people with plain set overlap instead of fuzzy text matching.
INTERESTS = [
    "agents",
    "llms",
    "rag",
    "mlops",
    "computer-vision",
    "data",
    "web",
    "mobile",
    "cloud",
    "devops",
    "security",
    "design",
    "startups",
    "open-source",
    "research",
    "gamedev",
    "fintech",
    "healthtech",
    "edtech",
]


class Role(str, Enum):
    student = "student"
    developer = "developer"
    designer = "designer"
    researcher = "researcher"
    founder = "founder"
    product = "product"
    other = "other"


class Goal(str, Enum):
    learn = "learn"
    mentor = "mentor"
    hire = "hire"
    get_hired = "get-hired"
    cofounder = "cofounder"
    collaborate = "collaborate"
    network = "network"


class Profile(BaseModel):
    """What the matchmaker and room-mates see. Never contains the raw sign-up text."""

    role: Role = Role.other
    interests: list[str] = Field(default_factory=list)
    goals: list[Goal] = Field(default_factory=list)
    one_liner: str = ""


class Attendee(BaseModel):
    id: str  # public id, safe to show to room-mates
    nickname: str
    about: str  # raw sign-up text; only the profile agent reads it
    profile: Profile
    contact: str | None = None  # revealed only on a mutual "let's stay in touch"


class Spot(BaseModel):
    """A physical meeting point configured by the organisers."""

    id: str
    name: str
    description: str = ""
    capacity: int = Field(gt=0)
    # Tile position on the virtual map; used by the UI, ignored by the agents.
    x: int | None = None
    y: int | None = None


class Meetup(BaseModel):
    spot_id: str
    spot_name: str
    spot_description: str
    meet_at: datetime
    until: datetime


class Room(BaseModel):
    id: str
    round: int
    member_ids: list[str]
    shared_interests: list[str]
    why: str
    icebreaker: str
    votes: list[str] = Field(default_factory=list)  # member ids who chose "meet in person"
    meetup: Meetup | None = None
