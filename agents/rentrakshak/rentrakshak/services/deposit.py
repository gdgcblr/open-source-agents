from __future__ import annotations

from rentrakshak.models.schemas import ExtractedProperty


def assess_deposit_terms(
    prop: ExtractedProperty,
    listing_text: str = "",
) -> dict:
    """Deterministic deposit guidance — no invented legal caps."""
    months = None
    if prop.monthly_rent_inr and prop.deposit_inr and prop.monthly_rent_inr > 0:
        months = round(prop.deposit_inr / prop.monthly_rent_inr, 1)

    notes = [
        "Deposit terms must be read from your written rental agreement.",
        "RentRakshak has not verified this property or owner.",
    ]
    if months is not None:
        if months > 6:
            notes.append(
                f"Stated deposit is about {months} months of rent — confirm refund conditions and timeline."
            )
        elif months < 1:
            notes.append("Deposit is less than one month rent — confirm what it covers.")
        else:
            notes.append(f"Stated deposit is about {months} months of rent — compare with agreement.")

    lower = listing_text.lower()
    if "non-refundable" in lower and "deposit" in lower:
        notes.append("Text mentions non-refundable deposit — clarify legally and in writing.")

    return {
        "deposit_inr": prop.deposit_inr,
        "monthly_rent_inr": prop.monthly_rent_inr,
        "approximate_months_of_rent": months,
        "legal_cap_claimed": False,
        "notes": notes,
        "limitations": [
            "No universal Karnataka deposit limit is asserted by this tool.",
        ],
    }
