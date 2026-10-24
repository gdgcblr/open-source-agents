from datetime import date

from lifeadmin_agent.evaluate import (
    _match_expected,
    _next_occurrence,
    _resolve_setup_reminders,
    _tool_sequence_matches,
)


def test_next_occurrence_selects_this_or_next_year():
    assert _next_occurrence("11-10", date(2026, 10, 24)) == "2026-11-10"
    assert _next_occurrence("11-10", date(2026, 11, 11)) == "2027-11-10"


def test_next_occurrence_handles_leap_day():
    assert _next_occurrence("02-29", date(2025, 3, 1)) == "2028-02-29"


def test_eval_argument_matching_supports_partial_and_contains():
    actual = {"title": "Renew vehicle insurance", "due_date": "2030-11-10"}
    expected = {"title": {"contains": "vehicle insurance"}, "due_date": "2030-11-10"}

    assert _match_expected(actual, expected, date(2026, 10, 24))
    assert not _match_expected(actual, {"due_date": "2030-11-11"}, date(2026, 10, 24))


def test_eval_setup_can_create_date_relative_to_today():
    reminders = _resolve_setup_reminders(
        [{"title": "Overdue bill", "days_from_today": -1}],
        date(2026, 10, 24),
    )

    assert reminders == [{"title": "Overdue bill", "due_date": "2026-10-23"}]


def test_eval_accepts_only_documented_tool_sequence_alternatives():
    actual = [
        {"name": "find_reminders", "args": {"query": "dentist appointment"}},
        {
            "name": "update_reminder",
            "args": {"due_date": "2030-05-12", "match_title": "Dentist appointment"},
        },
    ]
    alternative = [
        {"name": "find_reminders", "args": {"query": {"contains": "dentist"}}},
        {"name": "update_reminder", "args": {"due_date": "2030-05-12"}},
    ]

    assert _tool_sequence_matches(actual, alternative, date(2026, 10, 24))
    assert not _tool_sequence_matches(actual, alternative[:1], date(2026, 10, 24))
