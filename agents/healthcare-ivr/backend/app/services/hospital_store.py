"""Database persistence for the hospital's information and doctors, edited from the dashboard."""

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import Appointment, AppointmentStatus, DoctorRecord, HospitalRecord
from app.services.hospital import (
    Doctor,
    HospitalDataError,
    HospitalProfile,
    build_receptionist_prompt,
    check_unique_doctors,
    load_hospital_files,
)

HOSPITAL_ID = 1  # one hospital per deployment


def _to_doctor(record: DoctorRecord) -> Doctor:
    return Doctor(
        id=record.id,
        name=record.name,
        department=record.department,
        specialty=record.specialty,
        opd_days=tuple(record.opd_days),
        opd_start=record.opd_start,
        opd_end=record.opd_end,
        slot_minutes=record.slot_minutes,
        consultation_fee_inr=record.consultation_fee_inr,
    )


def _apply(record: DoctorRecord, doctor: Doctor, sort_order: int) -> None:
    record.name = doctor.name
    record.department = doctor.department
    record.specialty = doctor.specialty
    record.opd_days = list(doctor.opd_days)
    record.opd_start = doctor.opd_start
    record.opd_end = doctor.opd_end
    record.slot_minutes = doctor.slot_minutes
    record.consultation_fee_inr = doctor.consultation_fee_inr
    record.is_active = True
    record.sort_order = sort_order
    record.updated_at = datetime.now(UTC)


async def seed_hospital(db: AsyncSession, settings: Settings) -> bool:
    """Load ``HOSPITAL_DIR`` into the database on first start. Returns whether it seeded."""
    if await db.get(HospitalRecord, HOSPITAL_ID) is not None:
        return False
    profile = load_hospital_files(settings.hospital_dir)
    db.add(HospitalRecord(id=HOSPITAL_ID, name=profile.name, info_markdown=profile.info_markdown))
    for order, doctor in enumerate(profile.doctors):
        record = DoctorRecord(id=doctor.id)
        _apply(record, doctor, order)
        db.add(record)
    await db.commit()
    return True


async def load_hospital(db: AsyncSession) -> HospitalProfile:
    """The current hospital and its active doctors. Read per call, so edits apply immediately."""
    record = await db.get(HospitalRecord, HOSPITAL_ID)
    if record is None:
        raise HospitalDataError("No hospital data yet; restart the backend to seed it.")
    rows = await db.scalars(
        select(DoctorRecord)
        .where(DoctorRecord.is_active.is_(True))
        .order_by(DoctorRecord.sort_order, DoctorRecord.name)
    )
    return HospitalProfile(
        name=record.name,
        info_markdown=record.info_markdown,
        doctors=tuple(_to_doctor(row) for row in rows),
    )


async def update_hospital_info(
    db: AsyncSession, settings: Settings, *, name: str, markdown: str
) -> HospitalProfile:
    name, markdown = name.strip(), markdown.strip()
    if not name:
        raise HospitalDataError("The hospital needs a name.")
    if not markdown:
        raise HospitalDataError("The hospital information can't be empty.")

    candidate = (await load_hospital(db)).model_copy(
        update={"name": name, "info_markdown": markdown + "\n"}
    )
    build_receptionist_prompt(settings, candidate, datetime.now(UTC))  # rejects oversize data

    record = await db.get(HospitalRecord, HOSPITAL_ID)
    assert record is not None  # load_hospital succeeded above
    record.name = candidate.name
    record.info_markdown = candidate.info_markdown
    record.updated_at = datetime.now(UTC)
    await db.commit()
    return candidate


async def replace_doctors(
    db: AsyncSession, settings: Settings, doctors: list[Doctor], *, today: date
) -> HospitalProfile:
    """Make `doctors` the active roster, in order. Doctors left out are deactivated."""
    if not doctors:
        raise HospitalDataError("Keep at least one doctor on the roster.")
    roster = tuple(doctors)
    check_unique_doctors(roster, source="The roster")
    current = await load_hospital(db)
    build_receptionist_prompt(
        settings, current.model_copy(update={"doctors": roster}), datetime.now(UTC)
    )

    existing = {record.id: record for record in await db.scalars(select(DoctorRecord))}
    kept = {doctor.id for doctor in roster}
    removed = [r for r in existing.values() if r.is_active and r.id not in kept]
    if removed:
        busy = await db.scalars(
            select(Appointment.doctor_name)
            .where(
                Appointment.doctor_id.in_([record.id for record in removed]),
                Appointment.status == AppointmentStatus.BOOKED,
                Appointment.appointment_date >= today,
            )
            .distinct()
        )
        busy_names = sorted(busy)
        if busy_names:
            raise HospitalDataError(
                f"{', '.join(busy_names)} still has upcoming appointments. Cancel or move them "
                "before removing the doctor."
            )

    for order, doctor in enumerate(roster):
        record = existing.get(doctor.id)
        if record is None:
            record = DoctorRecord(id=doctor.id)
            db.add(record)
        _apply(record, doctor, order)
    for record in removed:
        record.is_active = False
        record.updated_at = datetime.now(UTC)
    await db.commit()
    return await load_hospital(db)
