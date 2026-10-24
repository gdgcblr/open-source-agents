import asyncio
from datetime import datetime, timedelta, timezone
import json

import pytest

from guardrails import model_context, validate_meeting
from mcp_client import get_slots
from scheduling import aware_datetime, find_slots


def test_slots_exclude_overlaps_but_allow_touching_boundaries():
    result = find_slots("2099-01-05", "2099-01-05", "UTC", 30, 9, 12,
                        [{"start": "2099-01-05T09:00:00Z", "end": "2099-01-05T10:00:00Z"}],
                        now="2099-01-01T00:00:00Z", include_weekends=True)
    assert result["slots"][0]["start"] == "2099-01-05T10:00:00+00:00"
    for slot in result["slots"]:
        assert aware_datetime(slot["end"]) - aware_datetime(slot["start"]) == timedelta(minutes=30)


def test_weekends_are_optional_and_timezone_offsets_are_preserved():
    assert not find_slots("2026-10-24", "2026-10-24", "Asia/Kolkata", 30, 9, 17, [], now="2026-10-23T00:00:00Z")["slots"]
    slots = find_slots("2026-10-24", "2026-10-24", "Asia/Kolkata", 30, 9, 17, [], now="2026-10-23T00:00:00Z", include_weekends=True)["slots"]
    assert slots[0]["start"].endswith("+05:30")


def test_dst_slots_have_correct_elapsed_duration():
    result = find_slots("2026-11-01", "2026-11-01", "America/New_York", 30, 0, 4, [],
                        now="2026-10-31T00:00:00Z", include_weekends=True)
    for slot in result["slots"]:
        assert aware_datetime(slot["end"]) - aware_datetime(slot["start"]) == timedelta(minutes=30)


def test_missing_offsets_and_invalid_intervals_are_rejected():
    with pytest.raises(ValueError):
        aware_datetime("2099-01-05T10:00:00")
    with pytest.raises(ValueError):
        find_slots("2099-01-05", "2099-01-05", "UTC", 30, 9, 17,
                   [{"start": "2099-01-05T11:00:00Z", "end": "2099-01-05T10:00:00Z"}])


def test_real_mcp_subprocess_returns_calculated_slots():
    day = str(datetime.now(timezone.utc).date() + timedelta(days=2))
    meeting = {"date_from": day, "date_to": day, "timezone": "UTC", "duration": 30,
               "hour_start": 9, "hour_end": 17, "include_weekends": True}
    result = asyncio.run(get_slots(meeting, []))
    assert len(result) == 6
    assert aware_datetime(result[0]["end"]) - aware_datetime(result[0]["start"]) == timedelta(minutes=30)


def test_model_context_excludes_email_addresses_and_extra_calendar_fields():
    result = model_context({"title": "Kickoff", "purpose": "Discuss with private@example.test",
                            "agenda": "Agree next steps", "duration": 30,
                            "attendees": ["invitee@example.test"], "busy": [{"secret": "private-calendar"}]}, "Please help")
    assert "@" not in result
    assert "private-calendar" not in result
    assert set(json.loads(result)) == {"title", "purpose", "agenda", "duration_minutes", "request"}
