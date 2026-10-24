"""Deterministic valuation engine. Every number shown to a user is computed here."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from portfolio import Holding, Portfolio, RatesData, Route

CATEGORIES = ("flights", "hotels", "cash", "shopping")
DISCLAIMER = "Indicative valuations for educational purposes — not financial advice."


@dataclass
class RouteValuation:
    card_id: str
    card_name: str
    route: Route
    points_used: int
    total_value_inr: float
    inr_per_point: float


def rank_routes(portfolio: Portfolio, rates: RatesData,
                category: str | None = None) -> list[RouteValuation]:
    vals: list[RouteValuation] = []
    for holding in portfolio.holdings:
        card = rates.cards[holding.card_id]
        for route in card.routes:
            if category is not None and route.category != category:
                continue
            if holding.points < route.min_points:
                continue
            total = round(holding.points * route.value_inr_per_point, 2)
            vals.append(RouteValuation(
                card_id=card.id, card_name=card.name, route=route,
                points_used=holding.points, total_value_inr=total,
                inr_per_point=route.value_inr_per_point))
    return sorted(vals, key=lambda v: v.inr_per_point, reverse=True)


def _cell(text: str, width: int) -> str:
    """Truncate with an ellipsis so a long name never overflows into the next column."""
    text = str(text)
    return text if len(text) <= width else text[: width - 1] + "…"


def format_table(valuations: list[RouteValuation], as_of: str) -> str:
    cw, rw = 36, 30     # card and route column widths (fit the longest real values)
    lines = [f"{'Card':<{cw}}{'Route':<{rw}}{'INR/pt':>7}{'Points':>9}{'Value INR':>13}"]
    lines.append("-" * (cw + rw + 29))
    for v in valuations:
        label = v.route.partner or v.route.id
        lines.append(f"{_cell(v.card_name, cw - 1):<{cw}}{_cell(label, rw - 1):<{rw}}"
                     f"{v.inr_per_point:>7.2f}{v.points_used:>9,}{v.total_value_inr:>13,.2f}")
    lines.append(f"\nRates as of {as_of}. {DISCLAIMER}")
    return "\n".join(lines)


@dataclass
class ExpiryAlert:
    card_id: str
    card_name: str
    points: int
    expires_on: date
    days_left: int
    best: RouteValuation | None


def expiring_points(portfolio: Portfolio, rates: RatesData,
                    today: date | None = None,
                    horizon_days: int = 90) -> list[ExpiryAlert]:
    today = today or date.today()
    alerts: list[ExpiryAlert] = []
    for holding in portfolio.holdings:
        card = rates.cards[holding.card_id]
        for batch in holding.batches:
            days_left = (batch.expires_on - today).days
            if days_left < 0 or days_left > horizon_days:
                continue
            batch_pf = Portfolio(holdings=[Holding(card_id=holding.card_id, points=batch.points)])
            ranked = rank_routes(batch_pf, rates)
            alerts.append(ExpiryAlert(
                card_id=card.id, card_name=card.name, points=batch.points,
                expires_on=batch.expires_on, days_left=days_left,
                best=ranked[0] if ranked else None))
    return sorted(alerts, key=lambda a: a.days_left)


def format_expiry(alerts: list[ExpiryAlert], as_of: str) -> str:
    if not alerts:
        return "No points expiring in the chosen horizon. " + DISCLAIMER
    lines = []
    for a in alerts:
        lines.append(f"[!] {a.card_name}: {a.points:,} points expire on "
                     f"{a.expires_on.isoformat()} ({a.days_left} days left)")
        if a.best is not None:
            label = a.best.route.partner or a.best.route.id
            lines.append(f"    best use: {label} at {a.best.inr_per_point:.2f} INR/pt "
                         f"~ INR {a.best.total_value_inr:,.2f}")
    lines.append(f"\nRates as of {as_of}. {DISCLAIMER}")
    return "\n".join(lines)
