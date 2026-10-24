from __future__ import annotations

import re

from rentrakshak.models.schemas import ExtractedProperty

LOCALITIES = [
    "whitefield",
    "marathahalli",
    "bellandur",
    "electronic city",
    "koramangala",
    "hsr layout",
    "indiranagar",
    "hebbal",
]

RENT_RE = re.compile(
    r"(?:monthly\s+)?rent\s*[:.]?\s*(?:₹|rs\.?|inr)?\s*(\d[\d,]{2,})\b",
    re.I,
)
DEPOSIT_RE = re.compile(
    r"deposit\s*[:.]?\s*(?:₹|rs\.?|inr)?\s*(\d[\d,]{2,})\b",
    re.I,
)
BHK_RE = re.compile(r"(\d)\s*bhk", re.I)
MAINT_RE = re.compile(
    r"maintenance\s*[:.]?\s*(?:₹\s*)?(\d{1,2}(?:,\d{3})*|\d{3,6})",
    re.I,
)


def _parse_inr(raw: str) -> int:
    return int(raw.replace(",", ""))


def extract_property(
    listing_text: str,
    *,
    locality_hint: str | None = None,
    monthly_rent_inr: int | None = None,
    deposit_inr: int | None = None,
    bhk: str | None = None,
    furnishing: str | None = None,
    maintenance_inr: int | None = None,
    property_type: str | None = None,
) -> ExtractedProperty:
    text = listing_text or ""
    lower = text.lower()

    locality = locality_hint
    if not locality:
        for loc in LOCALITIES:
            if loc in lower:
                locality = loc.title()
                break

    rent = monthly_rent_inr
    if rent is None:
        m = RENT_RE.search(text)
        if m:
            rent = _parse_inr(m.group(1))

    deposit = deposit_inr
    if deposit is None:
        m = DEPOSIT_RE.search(text)
        if m:
            deposit = _parse_inr(m.group(1))

    bhk_val = bhk
    if not bhk_val:
        m = BHK_RE.search(text)
        if m:
            bhk_val = f"{m.group(1)} BHK"

    furn = furnishing
    if not furn:
        if "fully furnished" in lower or "furnished" in lower:
            furn = "furnished"
        elif "semi" in lower and "furnish" in lower:
            furn = "semi-furnished"
        elif "unfurnished" in lower:
            furn = "unfurnished"

    maint = maintenance_inr
    if maint is None:
        m = MAINT_RE.search(text)
        if m:
            maint = _parse_inr(m.group(1))

    ptype = property_type
    if not ptype:
        for kw in ("pg", "shared room", "flat", "apartment", "independent house"):
            if kw in lower:
                ptype = kw
                break

    notes: list[str] = []
    if not locality:
        notes.append("Locality not identified from text.")
    if rent is None:
        notes.append("Monthly rent not found.")

    return ExtractedProperty(
        locality=locality,
        monthly_rent_inr=rent,
        deposit_inr=deposit,
        bhk=bhk_val,
        furnishing=furn,
        maintenance_inr=maint,
        property_type=ptype,
        raw_notes=notes,
    )


def find_contradictions(
    listing_text: str,
    chat_text: str | None,
    prop: ExtractedProperty,
) -> list[str]:
    issues: list[str] = []
    combined = f"{listing_text}\n{chat_text or ''}"

    rents = [_parse_inr(m.group(1)) for m in RENT_RE.finditer(combined)]
    if len(set(rents)) > 1:
        issues.append(f"Multiple rent figures mentioned: {sorted(set(rents))}")

    if prop.monthly_rent_inr and prop.deposit_inr:
        if prop.deposit_inr < prop.monthly_rent_inr:
            issues.append("Deposit is lower than one month's rent — confirm terms.")

    if chat_text:
        chat_lower = chat_text.lower()
        if "owner" in listing_text.lower() and "broker" in chat_lower:
            issues.append("Listing suggests owner but chat mentions broker.")
        if "broker" in listing_text.lower() and "i am the owner" in chat_lower:
            issues.append("Listing mentions broker but chat claims direct owner.")

    return issues
