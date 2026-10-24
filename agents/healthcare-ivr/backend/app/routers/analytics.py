"""Dashboard API: what the receptionist costs and what it converts into."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.dependencies import DbSession
from app.models import Appointment, AppointmentStatus, Call, CallSource
from app.schemas import AnalyticsSummary
from app.security import require_dashboard_user

router = APIRouter(
    prefix="/api/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_dashboard_user)],
)


def _ratio(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


@router.get("/summary")
async def get_summary(
    db: DbSession,
    days: Annotated[int, Query(ge=0, le=3650)] = 30,
) -> AnalyticsSummary:
    """Spend and conversions for calls placed, and appointments booked, in the last `days`.

    `days=0` means all time. A booking converts into revenue only when staff mark the
    appointment as attended, so revenue counts completed appointments only.
    """
    since = datetime.now(UTC) - timedelta(days=days) if days else None
    call_period = [Call.started_at >= since] if since else []
    booking_period = [Appointment.created_at >= since] if since else []

    phone_calls = await db.scalar(
        select(func.count()).where(Call.source == CallSource.PHONE, *call_period)
    )
    calls_by_language = {
        language or "unknown": count
        for language, count in (
            await db.execute(
                select(Call.language, func.count())
                .where(Call.source == CallSource.PHONE, *call_period)
                .group_by(Call.language)
            )
        ).all()
    }
    agent_seconds = await db.scalar(
        select(func.coalesce(func.sum(Call.agent_seconds), 0)).where(*call_period)
    )
    ai_cost = await db.scalar(
        select(
            func.coalesce(
                func.sum(
                    func.coalesce(Call.agent_cost_usd, 0)
                    + func.coalesce(Call.transcription_cost_usd, 0)
                ),
                0,
            )
        ).where(*call_period)
    )
    by_status = dict(
        (
            await db.execute(
                select(Appointment.status, func.count())
                .where(*booking_period)
                .group_by(Appointment.status)
            )
        ).all()
    )
    revenue = await db.scalar(
        select(func.coalesce(func.sum(Appointment.consultation_fee_inr), 0)).where(
            Appointment.status == AppointmentStatus.COMPLETED, *booking_period
        )
    )

    booked = sum(by_status.values())
    completed = by_status.get(AppointmentStatus.COMPLETED, 0)
    no_show = by_status.get(AppointmentStatus.NO_SHOW, 0)
    cost = round(float(ai_cost or 0), 4)
    return AnalyticsSummary(
        period_days=days or None,
        phone_calls=phone_calls or 0,
        calls_by_language=calls_by_language,
        voice_agent_minutes=round(float(agent_seconds or 0) / 60, 1),
        ai_cost_usd=cost,
        appointments_booked=booked,
        appointments_completed=completed,
        appointments_no_show=no_show,
        appointments_cancelled=by_status.get(AppointmentStatus.CANCELLED, 0),
        appointments_pending=by_status.get(AppointmentStatus.BOOKED, 0),
        revenue_inr=int(revenue or 0),
        booking_rate=_ratio(booked, phone_calls or 0),
        completion_rate=_ratio(completed, completed + no_show),
        cost_per_booking_usd=_ratio(cost, booked),
        cost_per_completed_usd=_ratio(cost, completed),
    )
