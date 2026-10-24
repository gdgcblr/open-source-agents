from datetime import date

import pytest

from ledger.parsing import format_date, format_money, parse_amount, parse_date


@pytest.mark.parametrize("raw,paise", [
    ("50000", 5_000_000), ("₹50,000.00", 5_000_000), ("Rs. 1,23,456.50", 12_345_650),
    ("INR 999.99", 99_999), ("$1,200", 120_000), (" 7 ", 700),
])
def test_parse_amount(raw, paise):
    assert parse_amount(raw) == paise


@pytest.mark.parametrize("raw", ["", "abc", "-500", "12.3.4"])
def test_parse_amount_rejects(raw):
    with pytest.raises(ValueError):
        parse_amount(raw)


def test_parse_date_formats_and_ambiguity():
    assert parse_date("2026-10-06") == (date(2026, 10, 6), False)
    assert parse_date("25/12/2026") == (date(2026, 12, 25), False)
    assert parse_date("03/04/2026") == (date(2026, 4, 3), True)
    assert parse_date("03/04/2026", day_first=False) == (date(2026, 3, 4), True)
    assert parse_date("05/05/2026")[1] is False  # same either way
    assert parse_date("6 Oct 2026") == (date(2026, 10, 6), False)
    with pytest.raises(ValueError):
        parse_date("31/31/2026")


@pytest.mark.parametrize("paise,currency,text", [
    (5_000_000, "INR", "₹50,000"), (12_345_678, "INR", "₹1,23,456.78"), (99_900, "INR", "₹999"),
    (1_000_000_000, "INR", "₹1,00,00,000"), (120_000, "USD", "$1,200"),
    (150_050, "AED", "AED 1,500.50"),
])
def test_format_money(paise, currency, text):
    assert format_money(paise, currency) == text


def test_format_date():
    assert format_date(date(2026, 9, 6)) == "6 Sep 2026"
