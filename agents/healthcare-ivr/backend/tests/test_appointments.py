import re
from collections.abc import AsyncIterator
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.db import SessionFactory, create_engine, create_session_factory, init_db
from app.models import Appointment, AppointmentStatus
from app.services.appointments import (
    BookingError,
    OutsideBookingWindowError,
    available_slots,
    book_appointment,
    check_day,
    find_doctor,
    next_free_slot,
    slot_times,
)
from app.services.hospital import Doctor, load_hospital_files
from tests.conftest import TEST_HOSPITAL_DIR

pytestmark = pytest.mark.anyio

PUNE = ZoneInfo("Asia/Kolkata")
MONDAY_8AM = datetime(2026, 10, 26, 8, 0, tzinfo=PUNE)
MONDAY = MONDAY_8AM.date()
WINDOW_HOURS = 72  # from Monday 8 AM: until Thursday 8 AM


@pytest.fixture
def doctors() -> tuple[Doctor, ...]:
    return load_hospital_files(TEST_HOSPITAL_DIR).doctors


@pytest.fixture
def asha(doctors: tuple[Doctor, ...]) -> Doctor:
    return doctors[0]  # Dr. Asha Rao: Mon, Wed, Fri, 09:00-10:00, 15-minute slots


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[SessionFactory]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'appointments.db'}")
    await init_db(engine)
    yield create_session_factory(engine)
    await engine.dispose()


async def _book(session_factory: SessionFactory, doctor: Doctor, start: time, **overrides):
    values = {
        "doctor": doctor,
        "day": MONDAY,
        "start": start,
        "patient_name": "Ravi Kumar",
        "patient_phone": "+919800000000",
        "patient_age": 42,
        "patient_gender": "male",
        "symptoms": "Chest tightness on stairs",
        "call_id": None,
        "now": MONDAY_8AM,
        "window_hours": WINDOW_HOURS,
        **overrides,
    }
    async with session_factory() as db:
        return await book_appointment(db, **values)


@pytest.mark.parametrize(
    ("query", "expected"),
    [("Dr. Asha Rao", "Dr. Asha Rao"), ("vikram", "Dr. Vikram Shah"), ("Shah", "Dr. Vikram Shah")],
)
def test_find_doctor_matches_full_and_partial_names(
    doctors: tuple[Doctor, ...], query: str, expected: str
) -> None:
    assert find_doctor(doctors, query).name == expected


def test_find_doctor_asks_which_doctor_when_ambiguous(doctors: tuple[Doctor, ...]) -> None:
    with pytest.raises(BookingError, match=re.escape("Dr. Asha Rao, Dr. Neha Rao")):
        find_doctor(doctors, "Dr. Rao")


def test_find_doctor_rejects_unknown_names(doctors: tuple[Doctor, ...]) -> None:
    with pytest.raises(BookingError, match=re.escape("No doctor named 'Dr. House'")):
        find_doctor(doctors, "Dr. House")


def test_slots_cover_the_opd_hours(asha: Doctor) -> None:
    assert slot_times(asha) == [time(9, 0), time(9, 15), time(9, 30), time(9, 45)]


@pytest.mark.parametrize(
    ("day", "message"),
    [
        (date(2026, 10, 23), "has already passed"),
        (date(2026, 10, 27), "no OPD on Tuesdays. Their OPD days are Monday, Wednesday, Friday"),
    ],
)
def test_days_outside_the_schedule_are_rejected(asha: Doctor, day: date, message: str) -> None:
    with pytest.raises(BookingError, match=re.escape(message)):
        check_day(asha, day, MONDAY_8AM)


async def test_available_slots_skip_booked_and_too_soon_times(
    session_factory: SessionFactory, asha: Doctor
) -> None:
    await _book(session_factory, asha, time(9, 45))

    async with session_factory() as db:
        early = await available_slots(db, asha, MONDAY, MONDAY_8AM, WINDOW_HOURS)
        # At 9:10 the 30-minute lead time rules out everything before 9:40.
        late = await available_slots(
            db, asha, MONDAY, MONDAY_8AM.replace(hour=9, minute=10), WINDOW_HOURS
        )

    assert early == [time(9, 0), time(9, 15), time(9, 30)]
    assert late == []


async def test_booking_saves_the_appointment(session_factory: SessionFactory, asha: Doctor) -> None:
    appointment = await _book(session_factory, asha, time(9, 15))

    assert len(appointment.reference) == 6
    assert not set(appointment.reference) & set("01IO")
    async with session_factory() as db:
        saved = await db.scalar(select(Appointment))
    assert saved is not None
    assert (saved.doctor_id, saved.appointment_date, saved.start_time) == (
        "dr-asha-rao",
        MONDAY,
        time(9, 15),
    )
    assert saved.status == AppointmentStatus.BOOKED
    assert (saved.patient_age, saved.patient_gender, saved.symptoms) == (
        42,
        "male",
        "Chest tightness on stairs",
    )


async def test_a_slot_cannot_be_booked_twice(session_factory: SessionFactory, asha: Doctor) -> None:
    await _book(session_factory, asha, time(9, 30))

    with pytest.raises(BookingError, match="just taken"):
        await _book(session_factory, asha, time(9, 30), patient_name="Someone Else")


async def test_cancelled_appointments_free_their_slot(
    session_factory: SessionFactory, asha: Doctor
) -> None:
    first = await _book(session_factory, asha, time(9, 0))
    async with session_factory() as db:
        cancelled = await db.get(Appointment, first.id)
        assert cancelled is not None
        cancelled.status = AppointmentStatus.CANCELLED
        await db.commit()

    rebooked = await _book(session_factory, asha, time(9, 0), patient_name="Next Patient")

    assert rebooked.reference != first.reference


@pytest.mark.parametrize(
    ("start", "now", "message"),
    [
        (time(9, 10), MONDAY_8AM, "isn't one of Dr. Asha Rao's appointment times"),
        (time(9, 0), MONDAY_8AM.replace(hour=8, minute=45), "too soon"),
    ],
)
async def test_invalid_times_are_rejected(
    session_factory: SessionFactory, asha: Doctor, start: time, now: datetime, message: str
) -> None:
    with pytest.raises(BookingError, match=re.escape(message)):
        await _book(session_factory, asha, start, now=now)


async def test_bookings_must_start_within_the_window(
    session_factory: SessionFactory, asha: Doctor
) -> None:
    wednesday = MONDAY + timedelta(days=2)  # within 72 hours of Monday 8 AM
    friday = MONDAY + timedelta(days=4)  # beyond them

    await _book(session_factory, asha, time(9, 0), day=wednesday)
    with pytest.raises(OutsideBookingWindowError, match="within the next 72 hours"):
        await _book(session_factory, asha, time(9, 0), day=friday)


async def test_next_free_slot_from_now_or_from_a_preferred_time(
    session_factory: SessionFactory, asha: Doctor
) -> None:
    await _book(session_factory, asha, time(9, 30))

    async with session_factory() as db:
        first = await next_free_slot(db, asha, MONDAY_8AM, WINDOW_HOURS)
        # 9:30 is taken, so asking for it gives the next free time after it.
        after_taken = await next_free_slot(
            db, asha, MONDAY_8AM, WINDOW_HOURS, datetime.combine(MONDAY, time(9, 30))
        )
        # Tuesday has no OPD, so the next free time is Wednesday's first slot.
        next_opd_day = await next_free_slot(
            db, asha, MONDAY_8AM, WINDOW_HOURS, datetime.combine(MONDAY, time(12, 0))
        )

    assert first == datetime.combine(MONDAY, time(9, 0))
    assert after_taken == datetime.combine(MONDAY, time(9, 45))
    assert next_opd_day == datetime.combine(MONDAY + timedelta(days=2), time(9, 0))


async def test_no_free_slot_in_the_window_is_reported(
    session_factory: SessionFactory, asha: Doctor
) -> None:
    friday_morning = datetime.combine(MONDAY + timedelta(days=4), time(9, 0))
    async with session_factory() as db:
        with pytest.raises(OutsideBookingWindowError, match="more than 72 hours away"):
            await next_free_slot(db, asha, MONDAY_8AM, WINDOW_HOURS, friday_morning)

    # Fill Monday and Wednesday, the only OPD days in the window.
    for day in (MONDAY, MONDAY + timedelta(days=2)):
        for slot in slot_times(asha):
            await _book(session_factory, asha, slot, day=day)
    async with session_factory() as db:
        with pytest.raises(OutsideBookingWindowError, match="no free time within the next 72"):
            await next_free_slot(db, asha, MONDAY_8AM, WINDOW_HOURS)
