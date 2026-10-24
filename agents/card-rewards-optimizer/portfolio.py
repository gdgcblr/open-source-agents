"""Dataclasses and validated loaders for the rates dataset and user portfolio."""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from datetime import date

import yaml


class PortfolioError(ValueError):
    """Raised for any invalid rates/portfolio input, with a human-readable message."""


@dataclass
class Route:
    id: str
    type: str                     # transfer | travel-portal | statement-credit | voucher
    category: str                 # flights | hotels | cash | shopping
    value_inr_per_point: float
    min_points: int = 0
    partner: str | None = None
    transfer_ratio: str | None = None
    description: str = ""


@dataclass
class CardInfo:
    id: str
    name: str
    issuer: str
    reward_currency: str
    routes: list[Route]


@dataclass
class RatesData:
    as_of: str
    cards: dict[str, CardInfo]


@dataclass
class Batch:
    points: int
    expires_on: date


@dataclass
class Holding:
    card_id: str
    points: int
    batches: list[Batch] = field(default_factory=list)


@dataclass
class Portfolio:
    holdings: list[Holding]


def load_rates(path: str) -> RatesData:
    with open(path) as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict) or "cards" not in raw or "as_of" not in raw:
        raise PortfolioError(f"{path}: expected top-level 'as_of' and 'cards' keys")
    if not isinstance(raw["cards"], dict):
        raise PortfolioError(f"{path}: 'cards' must be a mapping of card_id -> card details")
    cards: dict[str, CardInfo] = {}
    for card_id, c in raw["cards"].items():
        try:
            routes = [Route(**r) for r in c["routes"]]
            cards[card_id] = CardInfo(
                id=card_id, name=c["name"], issuer=c["issuer"],
                reward_currency=c["reward_currency"], routes=routes)
        except (KeyError, TypeError) as e:
            raise PortfolioError(f"{path}: card '{card_id}' is malformed: {e}") from e
    return RatesData(as_of=str(raw["as_of"]), cards=cards)


def _parse_date(value, card_id: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as e:
        raise PortfolioError(
            f"card '{card_id}': expires_on must be an ISO date (YYYY-MM-DD), got {value!r}") from e


def load_portfolio(path: str, rates: RatesData) -> Portfolio:
    with open(path) as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict) or "cards" not in raw:
        raise PortfolioError(f"{path}: expected a top-level 'cards' list")
    if not isinstance(raw["cards"], list):
        raise PortfolioError(
            f"{path}: 'cards' must be a list, got {type(raw['cards']).__name__}")
    holdings: list[Holding] = []
    for entry in raw["cards"]:
        if not isinstance(entry, dict):
            raise PortfolioError(f"{path}: each card entry must be a mapping, got {entry!r}")
        card_id = entry.get("card_id")
        if card_id not in rates.cards:
            hint = difflib.get_close_matches(str(card_id), rates.cards.keys(), n=1)
            suggest = f" Did you mean '{hint[0]}'?" if hint else ""
            raise PortfolioError(
                f"unknown card_id '{card_id}'. Valid ids: {sorted(rates.cards)}.{suggest}")
        points = entry.get("points")
        if isinstance(points, bool) or not isinstance(points, int) or points < 0:
            raise PortfolioError(f"card '{card_id}': points must be a non-negative integer")
        batches = []
        for b in entry.get("batches") or []:
            if not isinstance(b, dict) or "points" not in b or "expires_on" not in b:
                raise PortfolioError(
                    f"card '{card_id}': each batch needs 'points' and 'expires_on'")
            batches.append(Batch(points=int(b["points"]),
                                 expires_on=_parse_date(b["expires_on"], card_id)))
        holdings.append(Holding(card_id=card_id, points=points, batches=batches))
    return Portfolio(holdings=holdings)
