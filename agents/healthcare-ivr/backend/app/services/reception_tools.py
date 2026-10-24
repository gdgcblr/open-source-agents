"""Functions the receptionist can call during a conversation, via Deepgram function calling.

Deepgram asks the bridge to run a function with a `FunctionCallRequest`; the bridge calls
`run_tool` and returns the JSON result in a `FunctionCallResponse`. Every result is a dict the
LLM can read back to the caller, including errors, so a bad request never breaks the call. Each
call also leaves an event on the call's timeline, so staff can see what the receptionist did.

Two outcomes end the call, by asking the bridge to hang up after the receptionist's goodbye: a
caller who doesn't choose English or Hindi after `MAX_LANGUAGE_ATTEMPTS` answers, and a caller
who needs an appointment beyond the booking window (`BOOKING_WINDOW_HOURS`).
"""

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.db import SessionFactory
from app.models import Appointment, CallEventType
from app.services.appointments import (
    BookingError,
    OutsideBookingWindowError,
    book_appointment,
    cancel_appointment,
    check_phone,
    count_call_bookings,
    find_doctor,
    find_upcoming_appointments,
    next_free_slot,
    parse_day,
    parse_start_time,
)
from app.services.events import LiveFeed, record_event
from app.services.hospital import Doctor, HospitalProfile, format_time

logger = logging.getLogger(__name__)

# Languages the receptionist can speak, each with its own Deepgram voice.
LANGUAGES = {"en": "English", "hi": "Hindi"}
Gender = Literal["female", "male", "other", "prefer_not_to_say"]

_DOCTOR_NAME = {
    "type": "string",
    "description": "The doctor's name as it appears in the doctors list.",
}
_DATE = {"type": "string", "description": "The date as YYYY-MM-DD, in the hospital's timezone."}
_CONFIRMED = {
    "type": "boolean",
    "description": "True only if the caller clearly agreed to these details.",
}
_NAME_AS_SAID = {
    "type": "string",
    "description": (
        "The patient's full name as the caller says it, never from an earlier result. It must "
        "match the booking."
    ),
}

FUNCTION_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "set_language",
        "description": (
            "Record the language the caller chose. Use en for English and hi for Hindi, "
            "including a caller who simply speaks Hindi. If they ask for any other language, or "
            "their answer isn't a language, pass what they said, such as ta or unknown."
        ),
        # Changes the voice the caller hears, so only act on a confirmed turn.
        "defer_until_eot": True,
        "parameters": {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "description": "en, hi, or another language code, or unknown.",
                }
            },
            "required": ["language"],
        },
    },
    {
        "name": "find_slot",
        "description": (
            "Find a doctor's next free appointment time. Without a date, returns the next free "
            "time from now. With the day (and time) the caller prefers, returns that time if "
            "it's free, or the next free time after it. If nothing is free within the booking "
            "window, the call ends after your goodbye."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "doctor_name": _DOCTOR_NAME,
                "date": {**_DATE, "description": "The day the caller prefers, if they said one."},
                "time": {
                    "type": "string",
                    "description": "The time the caller prefers, as 24-hour HH:MM, if given.",
                },
            },
            "required": ["doctor_name"],
        },
    },
    {
        "name": "book_appointment",
        "description": (
            "Book an outpatient appointment. Only call this after reading the details back "
            "to the caller and hearing them clearly agree."
        ),
        # Changes data, so wait until Deepgram confirms the caller's turn has ended.
        "defer_until_eot": True,
        "parameters": {
            "type": "object",
            "properties": {
                "doctor_name": _DOCTOR_NAME,
                "date": _DATE,
                "time": {
                    "type": "string",
                    "description": "Start time as 24-hour HH:MM, from find_slot.",
                },
                "patient_name": {"type": "string", "description": "The patient's full name."},
                "patient_age": {"type": "integer", "description": "The patient's age in years."},
                "patient_gender": {"type": "string", "enum": list(get_args(Gender))},
                "patient_phone": {"type": "string", "description": "The patient's phone number."},
                "symptoms": {
                    "type": "string",
                    "description": "The patient's symptoms or reason for the visit, briefly.",
                },
                "caller_confirmed": _CONFIRMED,
            },
            "required": [
                "doctor_name",
                "date",
                "time",
                "patient_name",
                "patient_age",
                "patient_gender",
                "patient_phone",
                "symptoms",
                "caller_confirmed",
            ],
        },
    },
    {
        "name": "find_appointments",
        "description": (
            "Look up a patient's upcoming appointments, by booking reference or by phone number, "
            "plus the patient's name. With no reference or number, uses the number the caller is "
            "calling from."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "patient_name": _NAME_AS_SAID,
                "reference": {"type": "string", "description": "A booking reference, if given."},
                "patient_phone": {
                    "type": "string",
                    "description": "The phone number used to book, if not the caller's number.",
                },
            },
            "required": ["patient_name"],
        },
    },
    {
        "name": "cancel_appointment",
        "description": (
            "Cancel an upcoming appointment. Only call this after reading the appointment back "
            "and hearing the caller clearly agree."
        ),
        "defer_until_eot": True,
        "parameters": {
            "type": "object",
            "properties": {
                "reference": {"type": "string", "description": "The booking reference."},
                "patient_name": _NAME_AS_SAID,
                "caller_confirmed": _CONFIRMED,
            },
            "required": ["reference", "patient_name", "caller_confirmed"],
        },
    },
]


@dataclass
class CallState:
    """What the tools remember during one call."""

    unsupported_language_answers: int = 0


@dataclass(frozen=True)
class ToolContext:
    session_factory: SessionFactory
    settings: Settings
    hospital: HospitalProfile
    call_id: str | None  # events are only recorded when the tool runs during a call
    caller_number: str | None
    now: Callable[[], datetime]  # current time in the hospital's timezone
    feed: LiveFeed | None = None
    # Provided by the bridge while a call is connected: switch the agent's voice, and hang up
    # after the receptionist's next reply (its goodbye), giving the reason for the timeline.
    set_language: Callable[[str], Awaitable[None]] | None = None
    end_call: Callable[[str], Awaitable[None]] | None = None
    state: CallState = field(default_factory=CallState)


@dataclass(frozen=True)
class _Outcome:
    result: dict[str, Any]
    event: tuple[CallEventType, str] | None = None


def _when(day: date, start_time_label: str) -> str:
    return f"{day:%a %d %b} at {start_time_label}"


def _describe(appointment: Appointment) -> dict[str, Any]:
    return {
        "reference": appointment.reference,
        "doctor": appointment.doctor_name,
        "department": appointment.department,
        "day": f"{appointment.appointment_date:%A, %d %B %Y}",
        "time": format_time(appointment.start_time),
        "patient_name": appointment.patient_name,
    }


async def _end_call(context: ToolContext, reason: str) -> None:
    if context.end_call is not None:
        await context.end_call(reason)


# Length limits keep whatever the LLM passes (or a caller talks it into passing) to sane sizes.
_SHORT = 32  # dates, times, language codes
_NAME = 100
_PHONE = 20
_REFERENCE = 12
_SYMPTOMS = 300


class _SetLanguageArgs(BaseModel):
    language: str = Field(max_length=_SHORT)


class _FindSlotArgs(BaseModel):
    doctor_name: str = Field(max_length=_NAME)
    date: str | None = Field(default=None, max_length=_SHORT)
    time: str | None = Field(default=None, max_length=_SHORT)


class _BookAppointmentArgs(BaseModel):
    doctor_name: str = Field(max_length=_NAME)
    date: str = Field(max_length=_SHORT)
    time: str = Field(max_length=_SHORT)
    patient_name: str = Field(min_length=1, max_length=_NAME)
    patient_age: int = Field(ge=0, le=120)
    patient_gender: Gender
    patient_phone: str = Field(min_length=1, max_length=_PHONE)
    symptoms: str = Field(min_length=1, max_length=_SYMPTOMS)
    caller_confirmed: bool


class _FindAppointmentsArgs(BaseModel):
    reference: str | None = Field(default=None, max_length=_REFERENCE)
    patient_phone: str | None = Field(default=None, max_length=_PHONE)
    patient_name: str | None = Field(default=None, max_length=_NAME)


class _CancelAppointmentArgs(BaseModel):
    reference: str = Field(min_length=1, max_length=_REFERENCE)
    patient_name: str | None = Field(default=None, max_length=_NAME)
    caller_confirmed: bool


async def _set_language(arguments: dict[str, Any], context: ToolContext) -> _Outcome:
    args = _SetLanguageArgs.model_validate(arguments)
    language = args.language.strip().lower()
    if language not in LANGUAGES:
        return await _unsupported_language(language or "unknown", context)
    if context.set_language is None:
        raise BookingError("Switching language is only possible during a call.")
    await context.set_language(language)
    name = LANGUAGES[language]
    result: dict[str, Any] = {"language": language, "message": f"Reply in {name} from now on."}
    if language == "hi":
        result["message"] += " Write in Devanagari script."
    return _Outcome(result, (CallEventType.LANGUAGE_CHANGED, f"Switched to {name}"))


async def _unsupported_language(answer: str, context: ToolContext) -> _Outcome:
    context.state.unsupported_language_answers += 1
    count = context.state.unsupported_language_answers
    limit = context.settings.max_language_attempts
    if count >= limit:
        await _end_call(context, f"the caller didn't choose English or Hindi after {limit} tries")
        result = {
            "status": "ending_call",
            "message": (
                "Say in one short sentence that you can only help in English or Hindi, and "
                "goodbye. The call ends after that."
            ),
        }
    else:
        result = {
            "status": "not_supported",
            "message": "Only English and Hindi are available. Ask again: English or Hindi?",
        }
    message = f"Caller's answer '{answer}' wasn't English or Hindi ({count} of {limit})"
    return _Outcome(result, (CallEventType.LANGUAGE_NOT_SUPPORTED, message))


async def _outside_window(
    context: ToolContext, doctor: Doctor, error: OutsideBookingWindowError
) -> _Outcome:
    """Nothing can be booked in time, so the receptionist apologises and the call ends."""
    hours = context.settings.booking_window_hours
    await _end_call(context, f"no appointment with {doctor.name} within {hours} hours")
    result = {
        "status": "outside_booking_window",
        "message": (
            f"{error} Apologise, explain that, and say goodbye in one short sentence. The call "
            "ends after that."
        ),
    }
    message = f"No time with {doctor.name} within the {hours}-hour booking window"
    return _Outcome(result, (CallEventType.AVAILABILITY_CHECKED, message))


async def _find_slot(arguments: dict[str, Any], context: ToolContext) -> _Outcome:
    args = _FindSlotArgs.model_validate(arguments)
    doctor = find_doctor(context.hospital.doctors, args.doctor_name)
    requested: datetime | None = None
    if args.date:
        start = parse_start_time(args.time) if args.time else time.min
        requested = datetime.combine(parse_day(args.date), start)
    elif args.time:
        raise BookingError("Ask which day the caller wants, as well as the time.")

    try:
        async with context.session_factory() as db:
            slot = await next_free_slot(
                db, doctor, context.now(), context.settings.booking_window_hours, requested
            )
    except OutsideBookingWindowError as exc:
        return await _outside_window(context, doctor, exc)

    result: dict[str, Any] = {
        "doctor": doctor.name,
        "department": doctor.department,
        "date": slot.date().isoformat(),
        "time": f"{slot:%H:%M}",
        "day": f"{slot:%A, %d %B %Y}",
        "spoken_time": format_time(slot.time()),
    }
    if requested is not None and args.time:
        result["requested_time_free"] = slot == requested
    message = (
        f"Found {doctor.name}'s next free time: {_when(slot.date(), format_time(slot.time()))}"
    )
    return _Outcome(result, (CallEventType.AVAILABILITY_CHECKED, message))


async def _book_appointment(arguments: dict[str, Any], context: ToolContext) -> _Outcome:
    args = _BookAppointmentArgs.model_validate(arguments)
    if not args.caller_confirmed:
        raise BookingError("Not booked. Read the details back and ask the caller to confirm first.")
    phone = check_phone(args.patient_phone)

    doctor = find_doctor(context.hospital.doctors, args.doctor_name)
    day = parse_day(args.date)
    start = parse_start_time(args.time)
    async with context.session_factory() as db:
        limit = context.settings.max_bookings_per_call
        if context.call_id is not None and await count_call_bookings(db, context.call_id) >= limit:
            raise BookingError(
                f"Not booked. One call can book at most {limit} appointments. For more, give "
                "the caller the appointment and enquiry number."
            )
        try:
            appointment = await book_appointment(
                db,
                doctor=doctor,
                day=day,
                start=start,
                patient_name=args.patient_name.strip(),
                patient_phone=phone,
                patient_age=args.patient_age,
                patient_gender=args.patient_gender,
                symptoms=args.symptoms.strip(),
                call_id=context.call_id,
                now=context.now(),
                window_hours=context.settings.booking_window_hours,
            )
        except OutsideBookingWindowError as exc:
            return await _outside_window(context, doctor, exc)
    logger.info("Booked appointment %s on call %s", appointment.reference, context.call_id)
    result = {
        "status": "booked",
        **_describe(appointment),
        "patient_phone": appointment.patient_phone,
        "message": "Tell the caller the reference character by character.",
    }
    message = (
        f"Booked {appointment.reference}: {doctor.name}, {_when(day, format_time(start))}, "
        f"for {appointment.patient_name}"
    )
    return _Outcome(result, (CallEventType.APPOINTMENT_BOOKED, message))


def _required_name(value: str | None) -> str:
    """Lookups and cancellations need the patient's name: a caller ID can be spoofed and a
    booking reference overheard, so neither is enough on its own."""
    if not value or not value.strip():
        raise BookingError("Ask for the patient's full name as booked first.")
    return value


async def _find_appointments(arguments: dict[str, Any], context: ToolContext) -> _Outcome:
    args = _FindAppointmentsArgs.model_validate(arguments)
    patient_name = _required_name(args.patient_name)
    phone = args.patient_phone or context.caller_number
    async with context.session_factory() as db:
        appointments = await find_upcoming_appointments(
            db,
            today=context.now().date(),
            patient_name=patient_name,
            phone=phone,
            reference=args.reference,
        )
    result: dict[str, Any] = {"appointments": [_describe(a) for a in appointments]}
    if not appointments:
        result["message"] = (
            "No upcoming appointments found for that name. Check the name as booked, or ask for "
            "the booking reference."
        )
    looked_up = f"reference {args.reference.upper()}" if args.reference else "the phone number"
    count = f"{len(appointments)} upcoming" if appointments else "none upcoming"
    message = f"Looked up appointments by {looked_up}: {count}"
    return _Outcome(result, (CallEventType.APPOINTMENTS_LOOKED_UP, message))


async def _cancel_appointment(arguments: dict[str, Any], context: ToolContext) -> _Outcome:
    args = _CancelAppointmentArgs.model_validate(arguments)
    patient_name = _required_name(args.patient_name)
    if not args.caller_confirmed:
        raise BookingError(
            "Not cancelled. Read the appointment back and ask the caller to confirm."
        )
    async with context.session_factory() as db:
        appointment = await cancel_appointment(
            db,
            reference=args.reference,
            patient_name=patient_name,
            today=context.now().date(),
        )
    result = {"status": "cancelled", **_describe(appointment)}
    message = (
        f"Cancelled {appointment.reference}: {appointment.doctor_name}, "
        f"{_when(appointment.appointment_date, format_time(appointment.start_time))}"
    )
    return _Outcome(result, (CallEventType.APPOINTMENT_CANCELLED, message))


_HANDLERS: dict[str, Callable[[dict[str, Any], ToolContext], Awaitable[_Outcome]]] = {
    "set_language": _set_language,
    "find_slot": _find_slot,
    "book_appointment": _book_appointment,
    "find_appointments": _find_appointments,
    "cancel_appointment": _cancel_appointment,
}

# Collected for the booking only: they're stored on the appointment, never on the timeline.
_PRIVATE_FIELDS = frozenset({"patient_phone", "patient_age", "patient_gender", "symptoms"})


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[private]" if key in _PRIVATE_FIELDS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _validation_message(error: ValidationError) -> str:
    """Field names and problems, without echoing the values (which may be patient details)."""
    return "; ".join(
        f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
        for issue in error.errors(include_input=False, include_url=False)
    )


async def run_tool(name: str, arguments: str, context: ToolContext) -> dict[str, Any]:
    parsed: Any = None
    handler = _HANDLERS.get(name)
    if handler is None:
        outcome = _Outcome({"error": f"Unknown function '{name}'."})
    else:
        try:
            parsed = json.loads(arguments or "{}")
            if not isinstance(parsed, dict):
                raise ValueError("arguments must be a JSON object")
            outcome = await handler(parsed, context)
        except ValidationError as exc:
            outcome = _Outcome(
                {"error": f"Invalid arguments for {name}: {_validation_message(exc)}"}
            )
        except ValueError as exc:  # malformed JSON
            outcome = _Outcome({"error": f"Invalid arguments for {name}: {exc}"})
        except BookingError as exc:
            outcome = _Outcome({"error": str(exc)})

    event = outcome.event
    if event is None:
        event = (CallEventType.TOOL_ERROR, f"{name} failed: {outcome.result['error']}")
    if context.call_id is not None:
        data = {
            "function": name,
            "arguments": _redact(parsed) if isinstance(parsed, dict) else None,
            "result": _redact(outcome.result),
        }
        async with context.session_factory() as db:
            await record_event(
                db, context.call_id, event[0], event[1], data=data, feed=context.feed
            )
    return outcome.result
