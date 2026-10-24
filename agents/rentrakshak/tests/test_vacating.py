from datetime import date, timedelta

from rentrakshak.models.schemas import VacatingPostInput
from rentrakshak.services.vacating import (
    create_vacating_post,
    search_available_rooms,
    update_vacating_post_status,
)


def _post(**kwargs):
    base = {
        "locality": "Bellandur",
        "property_type": "apartment",
        "room_type": "private room",
        "monthly_rent_inr": 15000,
        "availability_date": date.today() + timedelta(days=14),
        "post_kind": "room_takeover",
        "description": "Vacating private room in shared 3BHK near ORR. Quiet flatmates.",
        "contact_method": "in-app-request",
    }
    base.update(kwargs)
    return VacatingPostInput(**base)


def test_active_post_searchable(tmp_db):
    out = create_vacating_post(_post(), publish=True, db_path=tmp_db)
    assert out["success"]
    results = search_available_rooms(locality="Bellandur", db_path=tmp_db)
    assert results["count"] == 1
    assert "contact_method_private" not in results["items"][0]


def test_draft_not_public(tmp_db):
    out = create_vacating_post(_post(), publish=False, db_path=tmp_db)
    assert out["status"] == "draft"
    results = search_available_rooms(locality="Bellandur", db_path=tmp_db)
    assert results["count"] == 0


def test_filled_excluded(tmp_db):
    out = create_vacating_post(_post(), publish=True, db_path=tmp_db)
    update_vacating_post_status(
        out["public_id"], out["edit_token"], "filled", db_path=tmp_db
    )
    results = search_available_rooms(locality="Bellandur", db_path=tmp_db)
    assert results["count"] == 0


def test_past_date_rejected(tmp_db):
    out = create_vacating_post(
        _post(availability_date=date.today() - timedelta(days=1)),
        publish=True,
        db_path=tmp_db,
    )
    assert not out["success"]


def test_unauthorized_edit(tmp_db):
    out = create_vacating_post(_post(), publish=True, db_path=tmp_db)
    bad = update_vacating_post_status(
        out["public_id"], "bad", "withdrawn", db_path=tmp_db
    )
    assert not bad["success"]
