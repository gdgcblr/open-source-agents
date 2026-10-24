from __future__ import annotations

import json
from pathlib import Path

from rentrakshak.config import package_root
from rentrakshak.models.schemas import ChecklistItem, ChecklistItemStatus, LegalSourceRef


def _load_legal() -> dict:
    path = package_root() / "data" / "legal_sources.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def get_karnataka_rental_guidance() -> list[LegalSourceRef]:
    data = _load_legal()
    refs = []
    for s in data.get("sources", []):
        refs.append(
            LegalSourceRef(
                title=s["title"],
                url=s["url"],
                section=s.get("section"),
                date_checked=s["date_checked"],
                scope=s["scope"],
                explanation=s["explanation"],
            )
        )
    return refs


def build_rental_checklist() -> list[ChecklistItem]:
    legal = get_karnataka_rental_guidance()
    primary = legal[0] if legal else None
    return [
        ChecklistItem(
            item_id="CHK-01",
            title="Confirm property address in person",
            description="Visit the unit and match address with listing and agreement.",
            category="practical_recommendation",
        ),
        ChecklistItem(
            item_id="CHK-02",
            title="Verify representative authority",
            description="Ask for ID and proof of authority to rent (owner/broker/manager).",
            category="practical_recommendation",
        ),
        ChecklistItem(
            item_id="CHK-03",
            title="Written rent and deposit terms",
            description="Rent, deposit, due dates, and payment mode must be in the agreement.",
            category="practical_recommendation",
        ),
        ChecklistItem(
            item_id="CHK-04",
            title="Deposit refund conditions",
            description="Document refund timeline, deductions, and handover process.",
            category="practical_recommendation",
        ),
        ChecklistItem(
            item_id="CHK-05",
            title="Maintenance and utilities",
            description="Clarify maintenance, water, power, and society charges.",
            category="practical_recommendation",
        ),
        ChecklistItem(
            item_id="CHK-06",
            title="Notice period and termination",
            description="Confirm notice period, lock-in, and exit penalties in writing.",
            category="practical_recommendation",
        ),
        ChecklistItem(
            item_id="CHK-07",
            title="Inventory and condition photos",
            description="Record fittings, appliances, and existing damage before move-in.",
            category="practical_recommendation",
        ),
        ChecklistItem(
            item_id="CHK-08",
            title="Agreement parties and signatures",
            description="All parties named in the agreement should sign; keep copies.",
            category="practical_recommendation",
        ),
        ChecklistItem(
            item_id="CHK-09",
            title="Payment records",
            description="Pay via traceable methods; keep receipts for deposit and rent.",
            category="practical_recommendation",
        ),
        ChecklistItem(
            item_id="CHK-10",
            title="Stamp duty / registration (if applicable)",
            description="Check whether your agreement needs stamp duty or registration under Karnataka rules.",
            category="official_guidance",
            source_title=primary.title if primary else None,
            source_url=primary.url if primary else None,
            source_section=primary.section if primary else None,
            date_checked=primary.date_checked if primary else None,
            status=ChecklistItemStatus.NEEDS_CLARIFICATION,
        ),
        ChecklistItem(
            item_id="CHK-11",
            title="Police verification (if applicable)",
            description="Some landlords request tenant verification — use official processes only.",
            category="official_guidance",
            status=ChecklistItemStatus.NEEDS_CLARIFICATION,
        ),
        ChecklistItem(
            item_id="CHK-12",
            title="Do not pay before adequate verification",
            description="Avoid token/advance until viewing and agreement review.",
            category="practical_recommendation",
        ),
    ]
