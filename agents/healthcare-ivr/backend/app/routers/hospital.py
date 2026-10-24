"""Dashboard API: view and edit the hospital information and doctors the receptionist uses."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError

from app.dependencies import DbSession, SettingsDep
from app.schemas import DoctorIn, DoctorOut, DoctorsUpdate, HospitalInfo, HospitalInfoUpdate
from app.security import require_dashboard_user
from app.services.hospital import Doctor, HospitalDataError, HospitalProfile
from app.services.hospital_store import load_hospital, replace_doctors, update_hospital_info

router = APIRouter(
    prefix="/api/hospital",
    tags=["hospital"],
    dependencies=[Depends(require_dashboard_user)],
)


def _hospital_out(hospital: HospitalProfile) -> HospitalInfo:
    return HospitalInfo(
        name=hospital.name,
        markdown=hospital.info_markdown,
        doctors=[
            DoctorOut(
                id=doctor.id,
                name=doctor.name,
                department=doctor.department,
                specialty=doctor.specialty,
                opd_weekdays=list(doctor.opd_days),
                opd_start=doctor.opd_start,
                opd_end=doctor.opd_end,
                slot_minutes=doctor.slot_minutes,
                consultation_fee_inr=doctor.consultation_fee_inr,
                opd_days=doctor.opd_days_label,
                opd_hours=doctor.opd_hours_label,
            )
            for doctor in hospital.doctors
        ],
    )


def _to_doctor(index: int, row: DoctorIn) -> Doctor:
    try:
        return Doctor(
            id=row.id,
            name=row.name,
            department=row.department,
            specialty=row.specialty,
            opd_days=tuple(row.opd_weekdays),
            opd_start=row.opd_start,
            opd_end=row.opd_end,
            slot_minutes=row.slot_minutes,
            consultation_fee_inr=row.consultation_fee_inr,
        )
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in error['loc']) or 'row'}: {error['msg']}"
            for error in exc.errors()
        )
        label = row.name.strip() or "unnamed"
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Doctor {index + 1} ({label}): {problems}"
        ) from exc


@router.get("")
async def get_hospital_info(db: DbSession) -> HospitalInfo:
    try:
        return _hospital_out(await load_hospital(db))
    except HospitalDataError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


@router.put("/info")
async def update_info(
    body: HospitalInfoUpdate, db: DbSession, settings: SettingsDep
) -> HospitalInfo:
    """Replace the hospital name and information. The next call uses the new version."""
    try:
        await update_hospital_info(db, settings, name=body.name, markdown=body.markdown)
        return _hospital_out(await load_hospital(db))
    except HospitalDataError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.put("/doctors")
async def update_doctors(body: DoctorsUpdate, db: DbSession, settings: SettingsDep) -> HospitalInfo:
    """Replace the roster. Doctors left out are removed unless they have upcoming bookings."""
    doctors = [_to_doctor(index, row) for index, row in enumerate(body.doctors)]
    today = datetime.now(ZoneInfo(settings.hospital_timezone)).date()
    try:
        return _hospital_out(await replace_doctors(db, settings, doctors, today=today))
    except HospitalDataError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
