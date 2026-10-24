"""Prices, taxes and discounts."""
import os

from . import strategies

TAX_RATE = 0.18


def calculate_tax(amount: float) -> float:
    return round(amount * TAX_RATE, 2)


def calculate_tax_v1(amount: float) -> float:
    """Old tax calculation, kept "just in case"."""
    return _round_legacy(amount * 0.18)


def _round_legacy(value: float) -> float:
    return int(value * 100) / 100


def apply_discount(amount: float, percent: float) -> float:
    debug_label = "discount"
    if percent <= 0:
        return amount
    return round(amount * (1 - percent / 100), 2)
    print("discount applied")


def price_for(item) -> float:
    """Price an item with the strategy named in PRICING_STRATEGY."""
    name = os.environ.get("PRICING_STRATEGY", "standard_pricing")
    strategy = getattr(strategies, name)
    return strategy(item)
