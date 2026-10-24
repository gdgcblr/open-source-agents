"""ORM models: calls with their transcripts and events, appointments, and the hospital."""

import enum
import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _enum_column[E: enum.Enum](enum_cls: type[E]) -> Enum:
    """Store enum *values* as plain strings so the schema stays portable across databases."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )


class CallSource(enum.StrEnum):
    PHONE = "phone"
    UPLOAD = "upload"


class CallStatus(enum.StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class DiarizationStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SpeakerRole(enum.StrEnum):
    AGENT = "agent"
    CUSTOMER = "customer"


class AppointmentStatus(enum.StrEnum):
    BOOKED = "booked"
    COMPLETED = "completed"  # the patient attended; this is what earns revenue
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class CallEventType(enum.StrEnum):
    """Things the system did during or after a call, shown on the call's timeline."""

    CALL_STARTED = "call_started"
    LANGUAGE_CHANGED = "language_changed"
    LANGUAGE_NOT_SUPPORTED = "language_not_supported"
    RECORDING_STARTED = "recording_started"
    RECORDING_FAILED = "recording_failed"
    AVAILABILITY_CHECKED = "availability_checked"
    APPOINTMENT_BOOKED = "appointment_booked"
    APPOINTMENTS_LOOKED_UP = "appointments_looked_up"
    APPOINTMENT_CANCELLED = "appointment_cancelled"
    APPOINTMENT_COMPLETED = "appointment_completed"
    APPOINTMENT_NO_SHOW = "appointment_no_show"
    TOOL_ERROR = "tool_error"
    AGENT_ERROR = "agent_error"
    TIME_LIMIT_REACHED = "time_limit_reached"
    AGENT_ENDED_CALL = "agent_ended_call"
    CALL_ENDED = "call_ended"
    RECORDING_RECEIVED = "recording_received"
    TRANSCRIPTION_COMPLETED = "transcription_completed"
    TRANSCRIPTION_FAILED = "transcription_failed"


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[CallSource] = mapped_column(_enum_column(CallSource))
    status: Mapped[CallStatus] = mapped_column(_enum_column(CallStatus))
    title: Mapped[str | None] = mapped_column(String(255))
    caller_number: Mapped[str | None] = mapped_column(String(32))
    # The hospital number the caller dialled; one deployment can answer several numbers.
    called_number: Mapped[str | None] = mapped_column(String(32))
    # Language the receptionist is speaking ("en" or "hi"); updated when the caller switches.
    language: Mapped[str | None] = mapped_column(String(8))
    twilio_call_sid: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    duration_seconds: Mapped[float | None] = mapped_column(Float)

    audio_filename: Mapped[str | None] = mapped_column(String(255))
    audio_content_type: Mapped[str | None] = mapped_column(String(100))

    diarization_status: Mapped[DiarizationStatus] = mapped_column(_enum_column(DiarizationStatus))
    diarization_error: Mapped[str | None] = mapped_column(Text)
    speaker_count: Mapped[int | None] = mapped_column(Integer)

    # Estimated AI cost, priced when the usage happens so later rate changes don't rewrite history.
    agent_seconds: Mapped[float | None] = mapped_column(Float)
    agent_cost_usd: Mapped[float | None] = mapped_column(Float)
    transcription_cost_usd: Mapped[float | None] = mapped_column(Float)

    # lazy="raise" forbids implicit IO in async code: load these explicitly with selectinload().
    turns: Mapped[list["TranscriptTurn"]] = relationship(
        back_populates="call",
        cascade="all, delete-orphan",
        order_by="TranscriptTurn.id",
        lazy="raise",
    )
    utterances: Mapped[list["Utterance"]] = relationship(
        back_populates="call",
        cascade="all, delete-orphan",
        order_by="Utterance.start",
        lazy="raise",
    )
    events: Mapped[list["CallEvent"]] = relationship(
        back_populates="call",
        cascade="all, delete-orphan",
        order_by="CallEvent.id",
        lazy="raise",
    )
    # Deleting a call keeps its appointments; the database clears their call_id.
    appointments: Mapped[list["Appointment"]] = relationship(
        back_populates="call",
        order_by="Appointment.created_at",
        passive_deletes=True,
        lazy="raise",
    )


class TranscriptTurn(Base):
    """One turn of the live conversation, as heard and spoken by the voice agent."""

    __tablename__ = "transcript_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)
    role: Mapped[SpeakerRole] = mapped_column(_enum_column(SpeakerRole))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)

    call: Mapped[Call] = relationship(back_populates="turns")


class Utterance(Base):
    """One speaker-attributed segment of the recording, produced by Deepgram diarization."""

    __tablename__ = "utterances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)
    speaker: Mapped[int] = mapped_column(Integer)
    start: Mapped[float] = mapped_column(Float)
    end: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)

    call: Mapped[Call] = relationship(back_populates="utterances")


class Appointment(Base):
    """An outpatient appointment, booked by the receptionist during a call."""

    __tablename__ = "appointments"
    __table_args__ = (
        # One active booking per doctor per slot; cancelled bookings free the slot again.
        Index(
            "uq_appointments_booked_slot",
            "doctor_id",
            "appointment_date",
            "start_time",
            unique=True,
            sqlite_where=text("status = 'booked'"),
            postgresql_where=text("status = 'booked'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reference: Mapped[str] = mapped_column(String(12), unique=True)
    call_id: Mapped[str | None] = mapped_column(
        ForeignKey("calls.id", ondelete="SET NULL"), index=True
    )
    doctor_id: Mapped[str] = mapped_column(String(100))
    doctor_name: Mapped[str] = mapped_column(String(200))
    department: Mapped[str] = mapped_column(String(200))
    # Local to the hospital's timezone.
    appointment_date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[time] = mapped_column(Time)
    # Patient details collected on the call. They're private: only staff see them, on the
    # dashboard, and they're left out of logs and timeline event data.
    patient_name: Mapped[str] = mapped_column(String(200))
    patient_phone: Mapped[str] = mapped_column(String(32))
    patient_age: Mapped[int | None] = mapped_column(Integer)
    patient_gender: Mapped[str | None] = mapped_column(String(24))
    symptoms: Mapped[str | None] = mapped_column(Text)
    # Fee at booking time, so revenue reports don't change when fees are edited later.
    consultation_fee_inr: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[AppointmentStatus] = mapped_column(
        _enum_column(AppointmentStatus), default=AppointmentStatus.BOOKED
    )
    status_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)

    call: Mapped[Call | None] = relationship(back_populates="appointments")


class CallEvent(Base):
    """One entry on a call's timeline: a tool the receptionist used, a booking, an error..."""

    __tablename__ = "call_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)
    type: Mapped[CallEventType] = mapped_column(_enum_column(CallEventType))
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)

    call: Mapped[Call] = relationship(back_populates="events")


class HospitalRecord(Base):
    """The hospital's editable information. Seeded from HOSPITAL_DIR on first start."""

    __tablename__ = "hospital"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    info_markdown: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)


class DoctorRecord(Base):
    """A doctor on the roster. Removed doctors are deactivated so past bookings keep context."""

    __tablename__ = "doctors"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    department: Mapped[str] = mapped_column(String(200))
    specialty: Mapped[str] = mapped_column(String(300), default="")
    opd_days: Mapped[list[int]] = mapped_column(JSON)  # weekday numbers, Monday is 0
    opd_start: Mapped[time] = mapped_column(Time)
    opd_end: Mapped[time] = mapped_column(Time)
    slot_minutes: Mapped[int] = mapped_column(Integer)
    consultation_fee_inr: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_utcnow)
