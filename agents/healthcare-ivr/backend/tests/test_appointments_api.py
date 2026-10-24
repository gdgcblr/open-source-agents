from datetime import date, time, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models import (
    Appointment,
    AppointmentStatus,
    Call,
    CallSource,
    CallStatus,
    DiarizationStatus,
)


def _add_appointment(
    client: TestClient,
    *,
    days_from_today: int,
    status: AppointmentStatus = AppointmentStatus.BOOKED,
) -> tuple[str, str]:
    """Create a call with one appointment; returns (call_id, appointment_id)."""

    async def add() -> tuple[str, str]:
        async with client.app.state.session_factory() as db:
            call = Call(
                source=CallSource.PHONE,
                status=CallStatus.COMPLETED,
                diarization_status=DiarizationStatus.SKIPPED,
            )
            appointment = Appointment(
                reference=f"R{days_from_today + 50:05d}",
                call=call,
                doctor_id="dr-asha-rao",
                doctor_name="Dr. Asha Rao",
                department="Cardiology",
                appointment_date=date.today() + timedelta(days=days_from_today),
                start_time=time(9, 0),
                patient_name="Ravi Kumar",
                patient_phone="+919811122233",
                consultation_fee_inr=1200,
                status=status,
            )
            db.add_all([call, appointment])
            await db.commit()
            return call.id, appointment.id

    return client.portal.call(add)


def _set_status(client: TestClient, appointment_id: str, status: str):
    return client.patch(f"/api/appointments/{appointment_id}", json={"status": status})


def test_attended_appointments_are_recorded_on_the_call(client: TestClient) -> None:
    call_id, appointment_id = _add_appointment(client, days_from_today=-1)

    response = _set_status(client, appointment_id, "completed")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["status_updated_at"] is not None
    events = client.get(f"/api/calls/{call_id}").json()["events"]
    assert (events[-1]["type"], events[-1]["message"]) == (
        "appointment_completed",
        f"Staff marked {body['reference']} as attended",
    )


def test_staff_can_cancel_an_upcoming_appointment(client: TestClient) -> None:
    _call_id, appointment_id = _add_appointment(client, days_from_today=3)

    response = _set_status(client, appointment_id, "cancelled")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_outcomes_can_be_corrected(client: TestClient) -> None:
    _call_id, appointment_id = _add_appointment(
        client, days_from_today=-2, status=AppointmentStatus.NO_SHOW
    )

    assert _set_status(client, appointment_id, "completed").json()["status"] == "completed"
    assert _set_status(client, appointment_id, "booked").json()["status"] == "booked"


@pytest.mark.parametrize(
    ("days_from_today", "starting", "new_status", "message"),
    [
        (2, AppointmentStatus.BOOKED, "completed", "on or before today"),
        (-1, AppointmentStatus.CANCELLED, "booked", "can't be marked booked"),
        (-1, AppointmentStatus.COMPLETED, "cancelled", "can't be marked cancelled"),
    ],
)
def test_impossible_outcomes_are_refused(
    client: TestClient,
    days_from_today: int,
    starting: AppointmentStatus,
    new_status: str,
    message: str,
) -> None:
    _call_id, appointment_id = _add_appointment(
        client, days_from_today=days_from_today, status=starting
    )

    response = _set_status(client, appointment_id, new_status)

    assert response.status_code == 409
    assert message in response.json()["detail"]


def test_unknown_appointments_are_not_found(client: TestClient) -> None:
    assert _set_status(client, "missing", "completed").status_code == 404
