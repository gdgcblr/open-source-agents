"""Load fictional demo data into SQLite."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from rentrakshak.config import default_db_path
from rentrakshak.db.database import init_db
from rentrakshak.models.schemas import AnonymousExperienceInput, VacatingPostInput
from rentrakshak.services.community import create_anonymous_experience
from rentrakshak.services.vacating import create_vacating_post

_DEMO_EXPERIENCES = [
    ("Koramangala", "apartment", "Deposit and refund", "negative", "35k-45k", "Deposit refund took 6 weeks; document every payment and follow up in writing."),
    ("Koramangala", "apartment", "Communication", "positive", "28k-32k", "Owner was responsive on maintenance tickets within 2-3 days. Clear agreement on notice period."),
    ("HSR Layout", "apartment", "Unexpected charges", "negative", "18k-22k", "Society escalation fee appeared after move-in though not in initial chat. Get all charges in the agreement."),
    ("HSR Layout", "pg", "Maintenance", "neutral", "12k-15k", "Decent PG but water timing issues on weekends. Rent was predictable."),
    ("Whitefield", "apartment", "General rental experience", "neutral", "30k-38k", "Long commute to central Bengaluru but flat was as described. Verify furnishing list at handover."),
    ("Whitefield", "apartment", "Move-out experience", "negative", "32k", "Painting charges deducted from deposit without prior walkthrough photos. Take dated pictures at move-in."),
    ("Indiranagar", "apartment", "Agreement clarity", "positive", "40k-55k", "Written addendum for maintenance and visitor policy helped avoid disputes."),
    ("Electronic City", "apartment", "Deposit and refund", "neutral", "16k-20k", "Refund came in 45 days. Keep bank transfer receipts for deposit."),
    ("Bellandur", "apartment", "Maintenance", "negative", "28k-34k", "Lift breakdown lasted two weeks; escalate to owner in email not only WhatsApp."),
    ("Marathahalli", "shared room", "Communication", "positive", "8k-10k", "Roommate and owner coordinated viewing slots well. Rent inclusive of WiFi as stated."),
    ("Hebbal", "apartment", "Unexpected charges", "negative", "22k-26k", "Parking fee added mid-lease. Ask about parking and society charges upfront."),
    ("Koramangala", "pg", "General rental experience", "positive", "14k", "Good for short internship stay; read food menu and curfew rules before paying."),
]

_DEMO_VACATING = [
    ("Whitefield", 16000, "Vacating furnished private room in 3BHK near ITPL road."),
    ("Koramangala", 22000, "1 BHK takeover from tenant leaving in 3 weeks; owner aware."),
    ("HSR Layout", 19000, "Shared flat private room; roommate replacement preferred."),
    ("Electronic City", 14000, "PG-style room with desk; ideal for Infosys campus commute."),
]


def seed_demo(db_path: Path | None = None) -> Path:
    db = db_path or default_db_path()
    if db.exists():
        db.unlink()
    init_db(db)

    for loc, ptype, cat, sent, band, text in _DEMO_EXPERIENCES:
        create_anonymous_experience(
            AnonymousExperienceInput(
                locality=loc,
                property_type=ptype,
                category=cat,
                sentiment=sent,
                rent_band=band,
                experience_text=text,
            ),
            db_path=db,
        )

    for i, (loc, rent, desc) in enumerate(_DEMO_VACATING):
        create_vacating_post(
            VacatingPostInput(
                locality=loc,
                property_type="apartment",
                room_type="private room",
                monthly_rent_inr=rent,
                availability_date=date.today() + timedelta(days=14 + i * 7),
                post_kind="room_takeover",
                description=desc,
                contact_method="demo-poster-contact",
                owner_permission_ack=True,
            ),
            publish=True,
            db_path=db,
        )
    return db
