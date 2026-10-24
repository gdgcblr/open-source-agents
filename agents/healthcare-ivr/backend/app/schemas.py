"""Pydantic response models for the dashboard API."""

from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models import (
    AppointmentStatus,
    CallEventType,
    CallSource,
    CallStatus,
    DiarizationStatus,
    SpeakerRole,
)


class TranscriptTurnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: SpeakerRole
    text: str
    created_at: datetime


class UtteranceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    speaker: int
    start: float
    end: float
    text: str
    confidence: float


class CallEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: CallEventType
    message: str
    created_at: datetime


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reference: str
    call_id: str | None
    doctor_name: str
    department: str
    appointment_date: date
    start_time: time
    patient_name: str
    patient_phone: str
    patient_age: int | None
    patient_gender: str | None
    symptoms: str | None
    consultation_fee_inr: int | None
    status: AppointmentStatus
    status_updated_at: datetime | None
    created_at: datetime


class AppointmentStatusUpdate(BaseModel):
    status: AppointmentStatus


class CallSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: CallSource
    status: CallStatus
    title: str | None
    caller_number: str | None
    called_number: str | None
    language: str | None
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: float | None
    diarization_status: DiarizationStatus
    speaker_count: int | None
    agent_seconds: float | None
    agent_cost_usd: float | None
    transcription_cost_usd: float | None
    audio_filename: str | None = Field(default=None, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_audio(self) -> bool:
        return self.audio_filename is not None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_cost_usd(self) -> float | None:
        """Estimated AI cost of the call so far; None until some usage has been priced."""
        parts = [c for c in (self.agent_cost_usd, self.transcription_cost_usd) if c is not None]
        return round(sum(parts), 4) if parts else None


class CallDetail(CallSummary):
    diarization_error: str | None
    turns: list[TranscriptTurnOut]
    utterances: list[UtteranceOut]
    appointments: list[AppointmentOut]
    events: list[CallEventOut]


class LiveCall(CallSummary):
    latest_turn: TranscriptTurnOut | None


class LiveCallList(BaseModel):
    items: list[LiveCall]


class CallPage(BaseModel):
    items: list[CallSummary]
    total: int
    page: int
    page_size: int
    total_cost_usd: float


class DoctorIn(BaseModel):
    """A roster row from the dashboard editor; `id` is empty for a new doctor."""

    id: str = ""
    name: str
    department: str
    specialty: str = ""
    opd_weekdays: list[int]
    opd_start: time
    opd_end: time
    slot_minutes: int
    consultation_fee_inr: int | None = None


class DoctorOut(DoctorIn):
    opd_days: str  # e.g. "Monday, Wednesday, Friday"
    opd_hours: str  # e.g. "9:00 AM to 1:00 PM"


class HospitalInfoUpdate(BaseModel):
    name: str
    markdown: str


class DoctorsUpdate(BaseModel):
    doctors: list[DoctorIn]


class HospitalInfo(BaseModel):
    name: str
    markdown: str
    doctors: list[DoctorOut]


class AppointmentList(BaseModel):
    items: list[AppointmentOut]


class AnalyticsSummary(BaseModel):
    """Spend and conversions for calls and bookings made in the period."""

    period_days: int | None  # None means all time
    phone_calls: int
    calls_by_language: dict[str, int]  # phone calls by the language they ended in
    voice_agent_minutes: float
    ai_cost_usd: float
    appointments_booked: int
    appointments_completed: int
    appointments_no_show: int
    appointments_cancelled: int
    appointments_pending: int  # still booked, outcome not recorded yet
    revenue_inr: int  # consultation fees of completed appointments
    booking_rate: float | None  # booked / phone calls
    completion_rate: float | None  # completed / (completed + no-shows)
    cost_per_booking_usd: float | None
    cost_per_completed_usd: float | None
