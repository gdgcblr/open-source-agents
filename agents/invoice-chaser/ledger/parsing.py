"""Parsing and formatting of money and dates. Money is always integer paise/cents."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_CURRENCY_NOISE = re.compile(r"(₹|rs\.?|inr|usd|\$|€|eur|,|\s)", re.IGNORECASE)
CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}


def parse_amount(raw: str) -> int:
    """'₹50,000.00' -> 5000000. Raises ValueError for empty/invalid/negative."""
    cleaned = _CURRENCY_NOISE.sub("", str(raw or ""))
    if not cleaned:
        raise ValueError("empty amount")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"not a number: {raw!r}") from None
    if value < 0:
        raise ValueError(f"negative amount: {raw!r}")
    return int((value * 100).quantize(Decimal("1")))


_DATE_FORMATS_DAY_FIRST = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d-%b-%Y", "%d %B %Y"]
_DATE_FORMATS_MONTH_FIRST = ["%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%d %b %Y", "%d-%b-%Y", "%d %B %Y"]
_NUMERIC_DATE = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-]\d{4}$")


def parse_date(raw: str, day_first: bool = True) -> tuple[date, bool]:
    """Returns (date, ambiguous). Ambiguous = both day/month <= 12 and different."""
    text = str(raw or "").strip()
    formats = _DATE_FORMATS_DAY_FIRST if day_first else _DATE_FORMATS_MONTH_FIRST
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        m = _NUMERIC_DATE.match(text)
        ambiguous = bool(m) and int(m[1]) <= 12 and int(m[2]) <= 12 and m[1] != m[2]
        return parsed, ambiguous
    raise ValueError(f"unrecognised date: {raw!r}")


def format_money(paise: int, currency: str) -> str:
    """Indian digit grouping for INR (₹1,23,456), western grouping otherwise."""
    whole, frac = divmod(paise, 100)
    if currency == "INR":
        s = str(whole)
        if len(s) > 3:
            head, tail = s[:-3], s[-3:]
            head = ",".join(re.findall(r"\d{1,2}", head[::-1]))[::-1]
            s = f"{head},{tail}"
    else:
        s = f"{whole:,}"
    symbol = CURRENCY_SYMBOLS.get(currency)
    amount = f"{s}.{frac:02d}" if frac else s
    return f"{symbol}{amount}" if symbol else f"{currency} {amount}"


def format_date(d: date) -> str:
    return f"{d.day} {d.strftime('%b %Y')}"
