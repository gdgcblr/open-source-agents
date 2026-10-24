from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime, timezone
from typing import Any

from rentrakshak.db.database import get_connection
from rentrakshak.guardrails.content_safety import check_public_post, redact_pii
from rentrakshak.models.schemas import VacatingPostInput


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _expire_old(conn) -> None:
    today = date.today().isoformat()
    conn.execute(
        """
        UPDATE vacating_posts
        SET status = 'expired', updated_at = ?
        WHERE status = 'active' AND availability_date < ?
        """,
        (_now(), today),
    )


def create_vacating_post(
    data: VacatingPostInput,
    *,
    publish: bool = False,
    db_path=None,
) -> dict[str, Any]:
    if data.availability_date < date.today():
        return {"success": False, "message": "availability_date cannot be in the past."}

    mod = check_public_post(data.description)
    if mod.status == "rejected":
        return {"success": False, "message": mod.user_message, "flags": mod.flags}

    desc, _ = redact_pii(mod.sanitized_text)
    contact_private = data.contact_method.strip()
    _, contact_pii = redact_pii(contact_private)
    if contact_pii:
        return {
            "success": False,
            "message": "Use in-app contact request; do not put phone/email in public description.",
        }

    public_id = str(uuid.uuid4())
    edit_token = secrets.token_urlsafe(32)
    status = "active" if publish else "draft"
    if publish and mod.status == "held":
        status = "pending_review"

    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO vacating_posts (
                public_id, edit_token, locality, property_type, room_type,
                monthly_rent_inr, deposit_inr, availability_date, furnishing,
                maintenance_inr, post_kind, description, viewing_windows,
                contact_method_private, owner_permission_ack, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                public_id,
                edit_token,
                data.locality.strip(),
                data.property_type.strip(),
                data.room_type.strip(),
                data.monthly_rent_inr,
                data.deposit_inr,
                data.availability_date.isoformat(),
                data.furnishing,
                data.maintenance_inr,
                data.post_kind,
                desc,
                data.viewing_windows,
                contact_private,
                1 if data.owner_permission_ack else 0,
                status,
                _now(),
                _now(),
            ),
        )

    return {
        "success": True,
        "public_id": public_id,
        "edit_token": edit_token,
        "status": status,
        "lease_safeguard": (
            "Confirm your agreement allows handover/sublet and obtain owner consent if required."
        ),
        "contact_privacy": "Contact details are not shown publicly; use edit_token to manage the post.",
    }


def search_available_rooms(
    locality: str | None = None,
    room_type: str | None = None,
    max_rent_inr: int | None = None,
    limit: int = 20,
    db_path=None,
) -> dict[str, Any]:
    limit = min(max(limit, 1), 50)
    with get_connection(db_path) as conn:
        _expire_old(conn)
        query = """
            SELECT public_id, locality, property_type, room_type, monthly_rent_inr,
                   deposit_inr, availability_date, furnishing, maintenance_inr,
                   post_kind, description, viewing_windows, status, created_at
            FROM vacating_posts
            WHERE status = 'active'
        """
        params: list[Any] = []
        if locality:
            query += " AND lower(locality) = lower(?)"
            params.append(locality.strip())
        if room_type:
            query += " AND lower(room_type) = lower(?)"
            params.append(room_type.strip())
        if max_rent_inr is not None:
            query += " AND monthly_rent_inr <= ?"
            params.append(max_rent_inr)
        query += " ORDER BY availability_date ASC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()

    return {
        "count": len(rows),
        "items": [dict(r) for r in rows],
        "limitations": [
            "Tenant-shared availability leads; not verified by RentRakshak.",
            "Not a guaranteed or legally transferable lease.",
        ],
    }


def update_vacating_post_status(
    public_id: str,
    edit_token: str,
    status: str,
    *,
    availability_date: date | None = None,
    db_path=None,
) -> dict[str, Any]:
    allowed = {"draft", "pending_review", "active", "filled", "withdrawn", "expired"}
    if status not in allowed:
        return {"success": False, "message": "Invalid status."}

    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT edit_token, status FROM vacating_posts WHERE public_id = ?",
            (public_id,),
        ).fetchone()
        if not row:
            return {"success": False, "message": "Not found."}
        if row["edit_token"] != edit_token:
            return {"success": False, "message": "Unauthorized."}

        if availability_date:
            if availability_date < date.today():
                return {"success": False, "message": "availability_date cannot be in the past."}
            conn.execute(
                """
                UPDATE vacating_posts
                SET availability_date = ?, updated_at = ?
                WHERE public_id = ?
                """,
                (availability_date.isoformat(), _now(), public_id),
            )

        conn.execute(
            """
            UPDATE vacating_posts SET status = ?, updated_at = ? WHERE public_id = ?
            """,
            (status, _now(), public_id),
        )
    return {"success": True, "status": status}


def request_contact(public_id: str, db_path=None) -> dict[str, Any]:
    """MVP: poster must share contact out-of-band; we do not expose stored contact publicly."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM vacating_posts WHERE public_id = ?",
            (public_id,),
        ).fetchone()
        if not row or row["status"] != "active":
            return {"success": False, "message": "Post not available."}
    return {
        "success": True,
        "message": (
            "Expression of interest recorded. For this MVP, the poster shares contact "
            "details privately using their chosen channel — not displayed here."
        ),
        "contact_disclosed": False,
    }
