import json
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.db import SessionFactory, create_engine, create_session_factory, init_db
from app.models import (
    Appointment,
    AppointmentStatus,
    Call,
    CallEvent,
    CallEventType,
    CallSource,
    CallStatus,
    DiarizationStatus,
)
from app.services.hospital import load_hospital_files
from app.services.reception_tools import FUNCTION_DEFINITIONS, ToolContext, run_tool
from tests.conftest import TEST_HOSPITAL_DIR, make_settings

pytestmark = pytest.mark.anyio

MONDAY_8AM = datetime(2026, 10, 26, 8, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
CALLER = "+919811122233"


@pytest.fixture
async def context(tmp_path: Path) -> AsyncIterator[ToolContext]:
    settings = make_settings(tmp_path)
    engine = create_engine(settings.database_url)
    await init_db(engine)
    session_factory = create_session_factory(engine)
    async with session_factory() as db:
        call = Call(
            source=CallSource.PHONE,
            status=CallStatus.IN_PROGRESS,
            caller_number=CALLER,
            diarization_status=DiarizationStatus.PENDING,
        )
        db.add(call)
        await db.commit()
    yield ToolContext(
        session_factory=session_factory,
        settings=settings,
        hospital=load_hospital_files(TEST_HOSPITAL_DIR),
        call_id=call.id,
        caller_number=CALLER,
        now=lambda: MONDAY_8AM,
    )
    await engine.dispose()


async def _appointments(session_factory: SessionFactory) -> list[Appointment]:
    async with session_factory() as db:
        return list(await db.scalars(select(Appointment)))


def _book_args(**overrides: object) -> str:
    args = {
        "doctor_name": "Dr. Asha Rao",
        "date": "2026-10-26",
        "time": "09:30",
        "patient_name": "Ravi Kumar",
        "patient_age": 42,
        "patient_gender": "male",
        "patient_phone": CALLER,
        "symptoms": "Chest tightness when climbing stairs",
        "caller_confirmed": True,
        **overrides,
    }
    return json.dumps(args)


async def _events(session_factory: SessionFactory) -> list[tuple[CallEventType, str]]:
    async with session_factory() as db:
        return [(e.type, e.message) for e in await db.scalars(select(CallEvent))]


def _find_slot(**args: str) -> str:
    return json.dumps({"doctor_name": "Dr. Asha Rao", **args})


@pytest.fixture
def ended() -> list[str]:
    """Reasons the tools asked the bridge to hang up."""
    return []


@pytest.fixture
def on_call(context: ToolContext, ended: list[str]) -> ToolContext:
    """The context as the bridge provides it during a call, with a recorded hang-up."""

    async def end_call(reason: str) -> None:
        ended.append(reason)

    async def switch(language: str) -> None:
        pass

    return replace(context, end_call=end_call, set_language=switch)


def test_changes_wait_for_the_end_of_the_callers_turn() -> None:
    functions = {f["name"]: f for f in FUNCTION_DEFINITIONS}

    for name in ("book_appointment", "cancel_appointment"):
        assert functions[name]["defer_until_eot"] is True
        assert "caller_confirmed" in functions[name]["parameters"]["required"]
    assert functions["set_language"]["defer_until_eot"] is True
    for name in ("find_slot", "find_appointments"):
        assert "defer_until_eot" not in functions[name]  # read-only, safe to run speculatively


def test_booking_needs_every_patient_detail() -> None:
    book = next(f for f in FUNCTION_DEFINITIONS if f["name"] == "book_appointment")

    required = set(book["parameters"]["required"])

    assert {
        "patient_name",
        "patient_age",
        "patient_gender",
        "patient_phone",
        "symptoms",
    } <= required


async def test_find_slot_offers_the_next_free_time(context: ToolContext) -> None:
    result = await run_tool("find_slot", _find_slot(), context)

    assert result == {
        "doctor": "Dr. Asha Rao",
        "department": "Cardiology",
        "date": "2026-10-26",
        "time": "09:00",
        "day": "Monday, 26 October 2026",
        "spoken_time": "9:00 AM",
    }


async def test_find_slot_checks_the_callers_preferred_time(context: ToolContext) -> None:
    await run_tool("book_appointment", _book_args(time="09:30"), context)

    taken = await run_tool("find_slot", _find_slot(date="2026-10-26", time="09:30"), context)
    free = await run_tool("find_slot", _find_slot(date="2026-10-26", time="09:00"), context)
    no_opd = await run_tool("find_slot", _find_slot(date="2026-10-27"), context)

    assert (taken["time"], taken["requested_time_free"]) == ("09:45", False)
    assert (free["time"], free["requested_time_free"]) == ("09:00", True)
    assert (no_opd["date"], no_opd["time"]) == ("2026-10-28", "09:00")  # Tuesday → Wednesday


async def test_times_beyond_72_hours_end_the_call(on_call: ToolContext, ended: list[str]) -> None:
    friday = await run_tool("find_slot", _find_slot(date="2026-10-30", time="09:00"), on_call)

    assert friday["status"] == "outside_booking_window"
    assert "more than 72 hours away" in friday["message"]
    assert "say goodbye" in friday["message"]
    assert ended == ["no appointment with Dr. Asha Rao within 72 hours"]


async def test_bookings_beyond_72_hours_are_refused(on_call: ToolContext, ended: list[str]) -> None:
    result = await run_tool("book_appointment", _book_args(date="2026-10-30"), on_call)

    assert result["status"] == "outside_booking_window"
    assert await _appointments(on_call.session_factory) == []
    assert len(ended) == 1


async def test_a_preferred_time_needs_a_day(context: ToolContext) -> None:
    result = await run_tool("find_slot", _find_slot(time="10:00"), context)

    assert "which day" in result["error"]


async def test_booking_saves_the_patient_details_and_links_the_call(context: ToolContext) -> None:
    result = await run_tool("book_appointment", _book_args(), context)

    assert result["status"] == "booked"
    assert result["time"] == "9:30 AM"
    assert result["day"] == "Monday, 26 October 2026"
    [appointment] = await _appointments(context.session_factory)
    assert appointment.reference == result["reference"]
    assert appointment.call_id == context.call_id
    assert (
        appointment.patient_name,
        appointment.patient_age,
        appointment.patient_gender,
        appointment.patient_phone,
        appointment.symptoms,
    ) == ("Ravi Kumar", 42, "male", CALLER, "Chest tightness when climbing stairs")


async def test_nothing_is_booked_without_the_callers_confirmation(context: ToolContext) -> None:
    result = await run_tool("book_appointment", _book_args(caller_confirmed=False), context)

    assert "confirm" in result["error"]
    assert await _appointments(context.session_factory) == []


async def test_taken_slots_are_reported_to_the_agent(context: ToolContext) -> None:
    await run_tool("book_appointment", _book_args(), context)

    second = await run_tool("book_appointment", _book_args(patient_name="Asha Patil"), context)

    assert "just taken" in second["error"]


async def test_one_call_can_only_book_a_few_appointments(context: ToolContext) -> None:
    capped = replace(
        context, settings=context.settings.model_copy(update={"max_bookings_per_call": 2})
    )
    for time in ("09:00", "09:15"):
        booked = await run_tool("book_appointment", _book_args(time=time), capped)
        assert booked["status"] == "booked"

    third = await run_tool("book_appointment", _book_args(time="09:30"), capped)

    assert "at most 2 appointments" in third["error"]
    assert len(await _appointments(context.session_factory)) == 2


@pytest.mark.parametrize("phone", ["call me back", "12345", "98111 22233 ext 4"])
async def test_booking_needs_a_real_phone_number(context: ToolContext, phone: str) -> None:
    result = await run_tool("book_appointment", _book_args(patient_phone=phone), context)

    assert "isn't a phone number" in result["error"]
    assert phone not in result["error"]
    assert await _appointments(context.session_factory) == []


@pytest.mark.parametrize(
    ("name", "arguments", "message"),
    [
        ("transfer_call", "{}", "Unknown function 'transfer_call'"),
        ("find_slot", "not json", "Invalid arguments"),
        (
            "book_appointment",
            json.dumps({"doctor_name": "Dr. Asha Rao"}),
            "symptoms: Field required",
        ),
        ("book_appointment", _book_args(patient_name="R" * 101), "at most 100 characters"),
        ("book_appointment", _book_args(symptoms="pain " * 61), "at most 300 characters"),
        ("book_appointment", _book_args(patient_age=130), "patient_age: Input should be less than"),
        ("book_appointment", _book_args(patient_gender="robot"), "patient_gender: Input should be"),
        ("find_appointments", json.dumps({"reference": "K" * 13}), "at most 12 characters"),
    ],
)
async def test_bad_requests_return_errors_instead_of_raising(
    context: ToolContext, name: str, arguments: str, message: str
) -> None:
    result = await run_tool(name, arguments, context)

    assert message in result["error"]


async def test_patient_details_stay_off_the_timeline(context: ToolContext) -> None:
    secret = "Recurring migraine " * 20  # too long, so the booking fails validation
    await run_tool("book_appointment", _book_args(), context)
    await run_tool("book_appointment", _book_args(time="09:45", symptoms=secret), context)

    async with context.session_factory() as db:
        booked, refused = list(await db.scalars(select(CallEvent)))
    assert booked.data is not None
    assert booked.data["arguments"]["patient_name"] == "Ravi Kumar"
    for field in ("patient_age", "patient_gender", "patient_phone", "symptoms"):
        assert booked.data["arguments"][field] == "[private]"
    assert booked.data["result"]["patient_phone"] == "[private]"
    # Validation errors name the field without repeating what the caller said.
    assert "Recurring migraine" not in refused.message
    assert "Recurring migraine" not in json.dumps(refused.data)


async def test_tool_calls_leave_events_on_the_call(context: ToolContext) -> None:
    await run_tool("find_slot", _find_slot(), context)
    booked = await run_tool("book_appointment", _book_args(), context)
    await run_tool("book_appointment", _book_args(caller_confirmed=False), context)

    assert await _events(context.session_factory) == [
        (
            CallEventType.AVAILABILITY_CHECKED,
            "Found Dr. Asha Rao's next free time: Mon 26 Oct at 9:00 AM",
        ),
        (
            CallEventType.APPOINTMENT_BOOKED,
            f"Booked {booked['reference']}: Dr. Asha Rao, Mon 26 Oct at 9:30 AM, for Ravi Kumar",
        ),
        (
            CallEventType.TOOL_ERROR,
            "book_appointment failed: Not booked. Read the details back and ask the caller to "
            "confirm first.",
        ),
    ]


async def test_find_appointments_uses_the_callers_number(context: ToolContext) -> None:
    booked = await run_tool("book_appointment", _book_args(), context)
    await run_tool(
        "book_appointment", _book_args(time="09:45", patient_phone="+919900000000"), context
    )

    mine = await run_tool("find_appointments", json.dumps({"patient_name": "Ravi Kumar"}), context)
    by_reference = await run_tool(
        "find_appointments",
        json.dumps({"reference": booked["reference"].lower(), "patient_name": "ravi kumar"}),
        context,
    )

    assert [a["reference"] for a in mine["appointments"]] == [booked["reference"]]
    assert mine["appointments"][0]["time"] == "9:30 AM"
    assert [a["reference"] for a in by_reference["appointments"]] == [booked["reference"]]


async def test_find_appointments_matches_numbers_in_any_format(context: ToolContext) -> None:
    await run_tool("book_appointment", _book_args(), context)  # booked as +919811122233

    found = await run_tool(
        "find_appointments",
        json.dumps({"patient_phone": "98111 22233", "patient_name": "Ravi Kumar"}),
        context,
    )

    assert len(found["appointments"]) == 1


async def test_lookups_need_the_patients_name(context: ToolContext) -> None:
    # A caller ID can be spoofed and a reference overheard, so neither is enough on its own.
    booked = await run_tool("book_appointment", _book_args(), context)

    def lookup(**args: str) -> Any:
        return run_tool("find_appointments", json.dumps(args), context)

    no_name = await lookup()
    wrong_name = await lookup(patient_name="Asha Patil")
    reference_wrong_name = await lookup(reference=booked["reference"], patient_name="Asha Patil")

    assert "patient's full name" in no_name["error"]
    assert wrong_name["appointments"] == []
    assert reference_wrong_name["appointments"] == []


async def test_withheld_caller_ids_find_nothing_without_a_number(context: ToolContext) -> None:
    await run_tool("book_appointment", _book_args(), context)
    withheld = replace(context, caller_number=None)

    result = await run_tool(
        "find_appointments", json.dumps({"patient_name": "Ravi Kumar"}), withheld
    )

    assert "booking reference or the phone number" in result["error"]


def _cancel_args(reference: str, **overrides: object) -> str:
    return json.dumps(
        {
            "reference": reference,
            "patient_name": "Ravi Kumar",
            "caller_confirmed": True,
            **overrides,
        }
    )


async def test_cancelling_frees_the_slot(context: ToolContext) -> None:
    booked = await run_tool("book_appointment", _book_args(), context)

    cancelled = await run_tool("cancel_appointment", _cancel_args(booked["reference"]), context)
    slot = await run_tool("find_slot", _find_slot(date="2026-10-26", time="09:30"), context)

    assert cancelled["status"] == "cancelled"
    [appointment] = await _appointments(context.session_factory)
    assert appointment.status == AppointmentStatus.CANCELLED
    assert slot["requested_time_free"] is True
    assert (await _events(context.session_factory))[-2][0] == CallEventType.APPOINTMENT_CANCELLED


async def test_cancelling_needs_confirmation(context: ToolContext) -> None:
    booked = await run_tool("book_appointment", _book_args(), context)

    result = await run_tool(
        "cancel_appointment", _cancel_args(booked["reference"], caller_confirmed=False), context
    )

    assert "confirm" in result["error"]
    [appointment] = await _appointments(context.session_factory)
    assert appointment.status == AppointmentStatus.BOOKED


async def test_cancelling_needs_the_patients_name_even_from_the_same_number(
    context: ToolContext,
) -> None:
    booked = await run_tool("book_appointment", _book_args(), context)
    reference = booked["reference"]
    other_caller = replace(context, caller_number="+918000000000")

    no_name = await run_tool(
        "cancel_appointment", _cancel_args(reference, patient_name=""), context
    )
    wrong_name = await run_tool(
        "cancel_appointment", _cancel_args(reference, patient_name="Asha Patil"), context
    )
    allowed = await run_tool(
        "cancel_appointment", _cancel_args(reference, patient_name="ravi KUMAR"), other_caller
    )

    assert "patient's full name" in no_name["error"]
    assert "doesn't match" in wrong_name["error"]
    assert allowed["status"] == "cancelled"


async def test_unknown_references_cannot_be_cancelled(context: ToolContext) -> None:
    result = await run_tool("cancel_appointment", _cancel_args("ZZZZZZ"), context)

    assert "No appointment has the reference ZZZZZZ" in result["error"]


async def test_set_language_switches_the_voice_and_logs_it(context: ToolContext) -> None:
    switched: list[str] = []

    async def switch(language: str) -> None:
        switched.append(language)

    result = await run_tool(
        "set_language", json.dumps({"language": "HI"}), replace(context, set_language=switch)
    )

    assert switched == ["hi"]
    assert result == {
        "language": "hi",
        "message": "Reply in Hindi from now on. Write in Devanagari script.",
    }
    assert (await _events(context.session_factory))[-1] == (
        CallEventType.LANGUAGE_CHANGED,
        "Switched to Hindi",
    )


async def test_three_answers_that_are_not_english_or_hindi_end_the_call(
    on_call: ToolContext, ended: list[str]
) -> None:
    def choose(language: str) -> Any:
        return run_tool("set_language", json.dumps({"language": language}), on_call)

    first = await choose("ta")
    second = await choose("unknown")
    assert first["status"] == second["status"] == "not_supported"
    assert ended == []

    third = await choose("Marathi")

    assert third["status"] == "ending_call"
    assert ended == ["the caller didn't choose English or Hindi after 3 tries"]
    refusals = [
        message
        for kind, message in await _events(on_call.session_factory)
        if kind == CallEventType.LANGUAGE_NOT_SUPPORTED
    ]
    assert refusals == [
        "Caller's answer 'ta' wasn't English or Hindi (1 of 3)",
        "Caller's answer 'unknown' wasn't English or Hindi (2 of 3)",
        "Caller's answer 'marathi' wasn't English or Hindi (3 of 3)",
    ]


async def test_language_can_only_change_during_a_call(context: ToolContext) -> None:
    result = await run_tool("set_language", json.dumps({"language": "hi"}), context)

    assert "only possible during a call" in result["error"]
