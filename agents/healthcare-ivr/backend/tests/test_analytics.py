from datetime import UTC, date, datetime, time, timedelta
from typing import Any

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

NOW = datetime.now(UTC)
_references = iter(f"REF{n:03d}" for n in range(1000))


def _call(*, days_ago: int = 1, agent_cost: float | None = 0.10, seconds: float = 60) -> Call:
    return Call(
        source=CallSource.PHONE,
        status=CallStatus.COMPLETED,
        started_at=NOW - timedelta(days=days_ago),
        diarization_status=DiarizationStatus.COMPLETED,
        agent_seconds=seconds,
        agent_cost_usd=agent_cost,
        transcription_cost_usd=0.005,
    )


def _appointment(
    status: AppointmentStatus, *, fee: int | None = 1000, days_ago: int = 1
) -> Appointment:
    return Appointment(
        reference=next(_references),
        doctor_id="dr-asha-rao",
        doctor_name="Dr. Asha Rao",
        department="Cardiology",
        appointment_date=date.today() - timedelta(days=days_ago),
        start_time=time(9, 0),
        patient_name="Patient",
        patient_phone="+919800000000",
        consultation_fee_inr=fee,
        status=status,
        created_at=NOW - timedelta(days=days_ago),
    )


def _seed(client: TestClient, *rows: Any) -> None:
    async def add() -> None:
        async with client.app.state.session_factory() as db:
            db.add_all(rows)
            await db.commit()

    client.portal.call(add)


def test_summary_counts_spend_conversions_and_revenue(client: TestClient) -> None:
    _seed(
        client,
        *[_call() for _ in range(4)],
        _appointment(AppointmentStatus.COMPLETED, fee=1200),
        _appointment(AppointmentStatus.COMPLETED, fee=800),
        _appointment(AppointmentStatus.NO_SHOW),
        _appointment(AppointmentStatus.BOOKED),
        _appointment(AppointmentStatus.CANCELLED),
    )

    summary = client.get("/api/analytics/summary").json()

    assert summary == {
        "period_days": 30,
        "phone_calls": 4,
        "calls_by_language": {"unknown": 4},
        "voice_agent_minutes": 4.0,
        "ai_cost_usd": 0.42,  # 4 x (0.10 agent + 0.005 transcription)
        "appointments_booked": 5,
        "appointments_completed": 2,
        "appointments_no_show": 1,
        "appointments_cancelled": 1,
        "appointments_pending": 1,
        "revenue_inr": 2000,  # only attended appointments earn revenue
        "booking_rate": 1.25,
        "completion_rate": 0.6667,  # 2 attended of 3 with a known outcome
        "cost_per_booking_usd": 0.084,
        "cost_per_completed_usd": 0.21,
    }


def test_summary_respects_the_period(client: TestClient) -> None:
    _seed(
        client,
        _call(days_ago=2),
        _call(days_ago=60),
        _appointment(AppointmentStatus.COMPLETED, days_ago=60),
    )

    recent = client.get("/api/analytics/summary", params={"days": 30}).json()
    all_time = client.get("/api/analytics/summary", params={"days": 0}).json()

    assert (recent["phone_calls"], recent["revenue_inr"]) == (1, 0)
    assert (all_time["period_days"], all_time["phone_calls"], all_time["revenue_inr"]) == (
        None,
        2,
        1000,
    )


def test_empty_summary_has_no_rates(client: TestClient) -> None:
    summary = client.get("/api/analytics/summary").json()

    assert summary["phone_calls"] == 0
    assert summary["booking_rate"] is None
    assert summary["completion_rate"] is None
    assert summary["cost_per_completed_usd"] is None


@pytest.mark.parametrize("days", [-1, 4000])
def test_invalid_periods_are_rejected(client: TestClient, days: int) -> None:
    assert client.get("/api/analytics/summary", params={"days": days}).status_code == 422


def test_summary_counts_calls_by_language(client: TestClient) -> None:
    english, hindi, also_hindi = _call(), _call(), _call()
    english.language, hindi.language, also_hindi.language = "en", "hi", "hi"
    _seed(client, english, hindi, also_hindi)

    summary = client.get("/api/analytics/summary").json()

    assert summary["calls_by_language"] == {"en": 1, "hi": 2}
