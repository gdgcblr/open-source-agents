from __future__ import annotations

from commute_gate.config import Settings
from commute_gate.routing.bengaluru import BengaluruRouteProvider
from commute_gate.routing.fixture import FixtureRouteProvider
from commute_gate.routing.huggingface import HuggingFaceRouteProvider


def get_route_provider(settings: Settings):
    if settings.route_provider == "fixture":
        return FixtureRouteProvider()
    if settings.route_provider == "huggingface":
        return HuggingFaceRouteProvider(settings.hf_dataset)
    if settings.route_provider == "bengaluru":
        return BengaluruRouteProvider()
    raise ValueError(
        f"Unknown ROUTE_PROVIDER={settings.route_provider!r}. "
        "Use 'bengaluru', 'fixture', or 'huggingface'."
    )
