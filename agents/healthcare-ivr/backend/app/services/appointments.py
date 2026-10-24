"""Outpatient appointments: availability, booking, lookup, cancellation and outcomes."""

import re
import secrets
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, AppointmentStatus
from app.services.hospital import WEEKDAY_NAMES, Doctor

# Booking references are read aloud, so leave out look-alike characters (0/O, 1/I).
_REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_REFERENCE_LENGTH = 6
# Same-day appointments must leave the patient time to reach the hospital.
MIN_LEAD_TIME = timedelta(minutes=30)


class BookingError(Exception):
    """A problem the receptionist should explain to the caller, e.g. a day the doctor is away."""


class OutsideBookingWindowError(BookingError):
    """The caller needs a time beyond the booking window, so the receptionist ends the call."""


def _normalize_name(value: str) -> list[str]:
    words = re.sub(r"[^a-z ]+", " ", value.lower()).split()
    return [word for word in words if word not in {"dr", "doctor"}]


def find_doctor(doctors: tuple[Doctor, ...], query: str) -> Doctor:
    """Match `Dr. Aditi Deshmukh`, `aditi deshmukh` or a unique surname like `Deshmukh`."""
    wanted = _normalize_name(query)
    if not wanted:
        raise BookingError("Ask the caller which doctor they want.")
    matches = [d for d in doctors if all(w in _normalize_name(d.name) for w in wanted)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        names = ", ".join(d.name for d in matches)
        raise BookingError(f"More than one doctor matches '{query}': {names}. Ask which one.")
    raise BookingError(f"No doctor named '{query}' is on the roster. Check the doctors list.")


def parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise BookingError(f"'{value}' is not a date in YYYY-MM-DD format.") from exc


def parse_start_time(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise BookingError(f"'{value}' is not a time in 24-hour HH:MM format.") from exc


def slot_times(doctor: Doctor) -> list[time]:
    """Every appointment start time in the doctor's OPD hours."""
    slots: list[time] = []
    current = datetime.combine(date.min, doctor.opd_start)
    last_start = datetime.combine(date.min, doctor.opd_end) - timedelta(minutes=doctor.slot_minutes)
    while current <= last_start:
        slots.append(current.time())
        current += timedelta(minutes=doctor.slot_minutes)
    return slots


def check_day(doctor: Doctor, day: date, now: datetime) -> None:
    """Reject days in the past or outside the doctor's OPD days."""
    if day < now.date():
        raise BookingError(f"{day:%d %B %Y} has already passed.")
    if day.weekday() not in doctor.opd_days:
        raise BookingError(
            f"{doctor.name} has no OPD on {WEEKDAY_NAMES[day.weekday()]}s. "
            f"Their OPD days are {doctor.opd_days_label}."
        )


def booking_deadline(now: datetime, window_hours: int) -> datetime:
    """The latest appointment start that can be booked, in the hospital's local time."""
    return (now + timedelta(hours=window_hours)).replace(tzinfo=None)


def _too_soon(day: date, start: time, now: datetime) -> bool:
    return datetime.combine(day, start) < (now + MIN_LEAD_TIME).replace(tzinfo=None)


async def _booked_times(db: AsyncSession, doctor: Doctor, day: date) -> set[time]:
    rows = await db.scalars(
        select(Appointment.start_time).where(
            Appointment.doctor_id == doctor.id,
            Appointment.appointment_date == day,
            Appointment.status == AppointmentStatus.BOOKED,
        )
    )
    return set(rows)


async def available_slots(
    db: AsyncSession, doctor: Doctor, day: date, now: datetime, window_hours: int
) -> list[time]:
    """Free start times for `doctor` on `day` within the booking window.

    `now` is the hospital's local time.
    """
    check_day(doctor, day, now)
    taken = await _booked_times(db, doctor, day)
    deadline = booking_deadline(now, window_hours)
    return [
        slot
        for slot in slot_times(doctor)
        if slot not in taken
        and not _too_soon(day, slot, now)
        and datetime.combine(day, slot) <= deadline
    ]


async def next_free_slot(
    db: AsyncSession,
    doctor: Doctor,
    now: datetime,
    window_hours: int,
    not_before: datetime | None = None,
) -> datetime:
    """The doctor's first free slot from `not_before` (hospital time, naive), or from now.

    Raises `OutsideBookingWindowError` when there's none within the booking window.
    """
    deadline = booking_deadline(now, window_hours)
    local_now = now.replace(tzinfo=None)
    earliest = max(not_before or local_now, local_now)
    day = earliest.date()
    while day <= deadline.date():
        if day.weekday() in doctor.opd_days:
            for slot in await available_slots(db, doctor, day, now, window_hours):
                if datetime.combine(day, slot) >= earliest:
                    return datetime.combine(day, slot)
        day += timedelta(days=1)
    if earliest > deadline:
        raise OutsideBookingWindowError(
            f"That time is more than {window_hours} hours away. Appointments can only be booked "
            f"within the next {window_hours} hours."
        )
    raise OutsideBookingWindowError(
        f"{doctor.name} has no free time within the next {window_hours} hours."
    )


def _new_reference() -> str:
    return "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(_REFERENCE_LENGTH))


async def book_appointment(
    db: AsyncSession,
    *,
    doctor: Doctor,
    day: date,
    start: time,
    patient_name: str,
    patient_phone: str,
    patient_age: int | None,
    patient_gender: str | None,
    symptoms: str | None,
    call_id: str | None,
    now: datetime,
    window_hours: int,
) -> Appointment:
    check_day(doctor, day, now)
    if start not in slot_times(doctor):
        raise BookingError(
            f"{start:%H:%M} isn't one of {doctor.name}'s appointment times. Slots start every "
            f"{doctor.slot_minutes} minutes from {doctor.opd_hours_label}."
        )
    if _too_soon(day, start, now):
        raise BookingError("That time is too soon to book. Offer a later slot.")
    if datetime.combine(day, start) > booking_deadline(now, window_hours):
        raise OutsideBookingWindowError(
            f"Appointments can only be booked within the next {window_hours} hours."
        )

    for _ in range(3):  # retry only for the (very unlikely) case of a duplicate reference
        appointment = Appointment(
            reference=_new_reference(),
            call_id=call_id,
            doctor_id=doctor.id,
            doctor_name=doctor.name,
            department=doctor.department,
            appointment_date=day,
            start_time=start,
            patient_name=patient_name,
            patient_phone=patient_phone,
            patient_age=patient_age,
            patient_gender=patient_gender,
            symptoms=symptoms,
            consultation_fee_inr=doctor.consultation_fee_inr,
        )
        db.add(appointment)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            if start in await _booked_times(db, doctor, day):
                raise BookingError("That time was just taken. Check availability again.") from None
            continue
        return appointment
    raise BookingError("The booking could not be saved. Ask the caller to call back.")


async def count_call_bookings(db: AsyncSession, call_id: str) -> int:
    """Active bookings made during one call, to cap how many slots a single call can take."""
    count = await db.scalar(
        select(func.count()).where(
            Appointment.call_id == call_id, Appointment.status == AppointmentStatus.BOOKED
        )
    )
    return count or 0


def check_phone(value: str) -> str:
    """Accept numbers like +91 98111 22233 or (020) 6721-5000: 7 to 15 digits, E.164's range."""
    value = value.strip()
    digit_count = len(re.sub(r"\D", "", value))
    if not re.fullmatch(r"\+?[\d\s().-]+", value) or not 7 <= digit_count <= 15:
        # The value isn't repeated: error messages end up on the call's timeline.
        raise BookingError(
            "That isn't a phone number I can book under. Ask the caller for their number again, "
            "digit by digit."
        )
    return value


def _phone_key(phone: str) -> str:
    """Compare numbers by their last ten digits, so +91 98111 22233 matches 9811122233."""
    return re.sub(r"\D", "", phone)[-10:]


def same_phone(first: str | None, second: str | None) -> bool:
    if not first or not second:
        return False
    key = _phone_key(first)
    return key != "" and key == _phone_key(second)


def _name_key(name: str) -> str:
    return " ".join(re.sub(r"[^a-z ]+", " ", name.lower()).split())


def same_name(first: str | None, second: str | None) -> bool:
    if not first or not second:
        return False
    key = _name_key(first)
    return key != "" and key == _name_key(second)


async def find_upcoming_appointments(
    db: AsyncSession,
    *,
    today: date,
    patient_name: str,
    phone: str | None = None,
    reference: str | None = None,
) -> list[Appointment]:
    """A patient's booked appointments from today on, by booking reference or phone number.

    The patient's name must match too: a caller ID can be spoofed and a reference overheard, so
    neither is enough on its own to hear someone's bookings.
    """
    query = (
        select(Appointment)
        .where(
            Appointment.status == AppointmentStatus.BOOKED,
            Appointment.appointment_date >= today,
        )
        .order_by(Appointment.appointment_date, Appointment.start_time)
    )
    if reference:
        rows = list(
            await db.scalars(query.where(Appointment.reference == reference.strip().upper()))
        )
    elif phone and _phone_key(phone):
        rows = [row for row in await db.scalars(query) if same_phone(row.patient_phone, phone)]
    else:
        raise BookingError("Ask for the booking reference or the phone number used to book.")
    return [row for row in rows if same_name(row.patient_name, patient_name)]


async def cancel_appointment(
    db: AsyncSession,
    *,
    reference: str,
    patient_name: str,
    today: date,
) -> Appointment:
    """Cancel an upcoming appointment, given its reference and the patient's name as booked."""
    appointment = await db.scalar(
        select(Appointment).where(Appointment.reference == reference.strip().upper())
    )
    if appointment is None:
        raise BookingError(f"No appointment has the reference {reference}.")
    if appointment.status != AppointmentStatus.BOOKED:
        raise BookingError(f"Appointment {appointment.reference} is already {appointment.status}.")
    if appointment.appointment_date < today:
        raise BookingError(f"Appointment {appointment.reference} has already passed.")

    if not same_name(patient_name, appointment.patient_name):
        raise BookingError(
            "The patient's name doesn't match this booking. Ask for the name exactly as booked."
        )

    appointment.status = AppointmentStatus.CANCELLED
    appointment.status_updated_at = datetime.now(UTC)
    await db.commit()
    return appointment


# Outcomes staff can record on the dashboard, and the statuses each one may follow.
_STAFF_TRANSITIONS: dict[AppointmentStatus, set[AppointmentStatus]] = {
    AppointmentStatus.COMPLETED: {AppointmentStatus.BOOKED, AppointmentStatus.NO_SHOW},
    AppointmentStatus.NO_SHOW: {AppointmentStatus.BOOKED, AppointmentStatus.COMPLETED},
    AppointmentStatus.CANCELLED: {AppointmentStatus.BOOKED},
    AppointmentStatus.BOOKED: {AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW},
}


def check_staff_transition(
    appointment: Appointment, new_status: AppointmentStatus, today: date
) -> None:
    if new_status == appointment.status:
        return
    if appointment.status not in _STAFF_TRANSITIONS[new_status]:
        raise BookingError(f"A {appointment.status} appointment can't be marked {new_status}.")
    attended_or_missed = {AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW}
    if new_status in attended_or_missed and appointment.appointment_date > today:
        raise BookingError("Only appointments on or before today can be marked attended or missed.")
