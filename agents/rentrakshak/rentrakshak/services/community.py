from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from rentrakshak.db.database import get_connection
from rentrakshak.guardrails.content_safety import check_public_post
from rentrakshak.models.schemas import AnonymousExperienceInput


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_anonymous_experience(
    data: AnonymousExperienceInput,
    db_path=None,
) -> dict[str, Any]:
    mod = check_public_post(data.experience_text)
    if mod.status == "rejected":
        return {
            "success": False,
            "moderation_status": mod.status,
            "message": mod.user_message,
            "flags": mod.flags,
        }

    public_id = str(uuid.uuid4())
    edit_token = secrets.token_urlsafe(32)
    status = "published" if mod.status == "published" else "pending_review"
    text = mod.sanitized_text

    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO experiences (
                public_id, edit_token, locality, property_type, rent_band, category,
                sentiment, experience_text, move_period, rating_maintenance,
                rating_communication, moderation_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                public_id,
                edit_token,
                data.locality.strip(),
                data.property_type.strip(),
                data.rent_band,
                data.category.strip(),
                data.sentiment,
                text,
                data.move_period,
                data.rating_maintenance,
                data.rating_communication,
                status,
                _now(),
                _now(),
            ),
        )
        if mod.flags:
            conn.execute(
                """
                INSERT INTO moderation_log (content_type, content_public_id, action, reason, created_at)
                VALUES ('experience', ?, 'flag', ?, ?)
                """,
                (public_id, ",".join(mod.flags), _now()),
            )

    return {
        "success": True,
        "public_id": public_id,
        "edit_token": edit_token,
        "moderation_status": status,
        "flags": mod.flags,
        "message": mod.user_message or "Experience submitted.",
        "privacy_note": "Save edit_token to update or delete; it is not shown publicly.",
    }


def search_anonymous_experiences(
    locality: str | None = None,
    category: str | None = None,
    property_type: str | None = None,
    sentiment: str | None = None,
    limit: int = 20,
    db_path=None,
) -> dict[str, Any]:
    limit = min(max(limit, 1), 50)
    query = """
        SELECT public_id, locality, property_type, rent_band, category, sentiment,
               experience_text, move_period, rating_maintenance, rating_communication,
               moderation_status, created_at
        FROM experiences
        WHERE is_deleted = 0 AND moderation_status = 'published'
    """
    params: list[Any] = []
    if locality:
        query += " AND lower(locality) = lower(?)"
        params.append(locality.strip())
    if category:
        query += " AND lower(category) = lower(?)"
        params.append(category.strip())
    if property_type:
        query += " AND lower(property_type) = lower(?)"
        params.append(property_type.strip())
    if sentiment:
        query += " AND sentiment = ?"
        params.append(sentiment)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with get_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()

    items = [dict(r) for r in rows]
    return {
        "count": len(items),
        "items": items,
        "limitations": [
            "User-submitted anonymous experiences; not verified facts.",
            "Sample is self-selected and not statistically representative.",
        ],
    }


def delete_experience(public_id: str, edit_token: str, db_path=None) -> dict[str, Any]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT edit_token FROM experiences WHERE public_id = ? AND is_deleted = 0",
            (public_id,),
        ).fetchone()
        if not row:
            return {"success": False, "message": "Not found."}
        if row["edit_token"] != edit_token:
            return {"success": False, "message": "Unauthorized."}
        conn.execute(
            "UPDATE experiences SET is_deleted = 1, updated_at = ? WHERE public_id = ?",
            (_now(), public_id),
        )
    return {"success": True, "message": "Experience withdrawn."}


def report_community_content(
    content_type: str,
    content_public_id: str,
    reason: str,
    db_path=None,
) -> dict[str, Any]:
    if content_type not in ("experience", "vacating_post"):
        return {"success": False, "message": "Invalid content_type."}
    if len(reason.strip()) < 10:
        return {"success": False, "message": "Reason too short."}
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO content_reports (content_type, content_public_id, reason, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (content_type, content_public_id, reason.strip()[:500], _now()),
        )
    return {"success": True, "message": "Report recorded for moderation review."}


def summarize_community_for_locality(locality: str, db_path=None) -> dict[str, Any]:
    result = search_anonymous_experiences(locality=locality, limit=50, db_path=db_path)
    items = result["items"]
    if not items:
        return {
            "locality": locality,
            "submission_count": 0,
            "recurring_themes": [],
            "limitations": result["limitations"],
        }
    categories: dict[str, int] = {}
    for it in items:
        categories[it["category"]] = categories.get(it["category"], 0) + 1
    themes = sorted(categories.items(), key=lambda x: -x[1])[:3]
    return {
        "locality": locality,
        "submission_count": len(items),
        "recurring_themes": [{"category": k, "count": v} for k, v in themes],
        "limitations": result["limitations"]
        + ([f"Only {len(items)} published posts — patterns are indicative, not proof."] if len(items) < 5 else []),
    }
