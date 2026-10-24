"""Dashboard API: appointments the receptionist booked, and their outcomes."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.dependencies import DbSession, SettingsDep
from app.models import Appointment, AppointmentStatus, CallEventType
from app.schemas import AppointmentList, AppointmentOut, AppointmentStatusUpdate
from app.security import require_dashboard_user
from app.services.appointments import BookingError, check_staff_transition
from app.services.events import record_event

router = APIRouter(
    prefix="/api/appointments",
    tags=["appointments"],
    dependencies=[Depends(require_dashboard_user)],
)

_STATUS_EVENTS = {
    AppointmentStatus.COMPLETED: (CallEventType.APPOINTMENT_COMPLETED, "attended"),
    AppointmentStatus.NO_SHOW: (CallEventType.APPOINTMENT_NO_SHOW, "a no-show"),
    AppointmentStatus.CANCELLED: (CallEventType.APPOINTMENT_CANCELLED, "cancelled"),
}


@router.get("")
async def list_appointments(
    db: DbSession,
    settings: SettingsDep,
    scope: Annotated[Literal["upcoming", "past"], Query()] = "upcoming",
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> AppointmentList:
    """Upcoming appointments soonest first, or past ones most recent first."""
    today = datetime.now(ZoneInfo(settings.hospital_timezone)).date()
    query = select(Appointment)
    if scope == "upcoming":
        query = query.where(Appointment.appointment_date >= today).order_by(
            Appointment.appointment_date, Appointment.start_time
        )
    else:
        query = query.where(Appointment.appointment_date < today).order_by(
            Appointment.appointment_date.desc(), Appointment.start_time.desc()
        )
    rows = await db.scalars(query.limit(limit))
    return AppointmentList(items=[AppointmentOut.model_validate(row) for row in rows])


@router.patch("/{appointment_id}")
async def update_appointment_status(
    appointment_id: str, body: AppointmentStatusUpdate, db: DbSession, settings: SettingsDep
) -> AppointmentOut:
    """Record what happened: attended (which earns revenue), a no-show, or a cancellation."""
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")
    today = datetime.now(ZoneInfo(settings.hospital_timezone)).date()
    try:
        check_staff_transition(appointment, body.status, today)
    except BookingError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    if body.status != appointment.status:
        appointment.status = body.status
        appointment.status_updated_at = datetime.now(UTC)
        await db.commit()
        if appointment.call_id and body.status in _STATUS_EVENTS:
            event_type, outcome = _STATUS_EVENTS[body.status]
            await record_event(
                db,
                appointment.call_id,
                event_type,
                f"Staff marked {appointment.reference} as {outcome}",
            )
    return AppointmentOut.model_validate(appointment)
