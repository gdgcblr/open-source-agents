import pytest


def calculate_discount(price, discount_percent):
    if price < 0:
        raise ValueError("Price cannot be negative")

    if not 0 <= discount_percent <= 100:
        raise ValueError("Discount must be between 0 and 100")

    return price * (1 - discount_percent / 100)


def test_invalid_discount_price_raises_expected_exception():
    # This regular unit test stays green while proving the error is traceable.
    with pytest.raises(ValueError, match="Price cannot be negative"):
        calculate_discount(-100, 10)
