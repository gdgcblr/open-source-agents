"""Loads the organiser's event file (rooms, timings and physical meeting spots)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from .models import Spot


class EventConfig(BaseModel):
    name: str
    room_size: int = Field(default=5, ge=2)
    walk_minutes: int = Field(default=3, ge=0)  # time to walk to a spot before the meetup starts
    meetup_minutes: int = Field(default=10, ge=1)  # how long a group holds a spot
    max_wait_minutes: int = Field(default=30, ge=0)  # give up rather than schedule further out
    spots: list[Spot]

    @model_validator(mode="after")
    def _check_spots(self) -> EventConfig:
        ids = [s.id for s in self.spots]
        if len(ids) != len(set(ids)):
            raise ValueError("spot ids must be unique")
        too_small = [s.id for s in self.spots if s.capacity < self.room_size]
        if too_small:
            raise ValueError(f"spots smaller than room_size can never host a room: {too_small}")
        return self


def load_config(path: str | Path) -> EventConfig:
    data = yaml.safe_load(Path(path).read_text())
    return EventConfig(**data["event"], spots=data["spots"])
