"""Pricing strategies, chosen by name at runtime (see pricing.price_for)."""


def standard_pricing(item) -> float:
    return item.unit_price


def premium_pricing(item) -> float:
    return round(item.unit_price * 1.25, 2)
