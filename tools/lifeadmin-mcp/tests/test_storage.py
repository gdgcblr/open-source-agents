from datetime import date, timedelta

import pytest

from lifeadmin_mcp import storage


def test_reminder_crud_and_persistence(tmp_path, monkeypatch):
    database = tmp_path / "reminders.sqlite3"
    monkeypatch.setenv("LIFEADMIN_DB_PATH", str(database))

    created = storage.add_reminder(
        "  Renew vehicle insurance ",
        "2030-11-10",
        category="documents",
        notes="Compare providers",
    )
    assert created["title"] == "Renew vehicle insurance"
    assert created["status"] == "open"
    assert storage.list_reminders("all")[0]["id"] == created["id"]

    updated = storage.update_reminder(
        created["id"],
        due_date="2030-11-12",
        due_time="09:30",
    )
    assert updated["due_date"] == "2030-11-12"
    assert updated["due_time"] == "09:30"
    assert updated["notes"] == "Compare providers"

    cleared = storage.update_reminder(created["id"], clear_due_time=True, notes="")
    assert cleared["due_time"] is None
    assert cleared["notes"] == ""

    completed = storage.mark_completed(created["id"])
    assert completed["status"] == "completed"
    assert storage.list_reminders("upcoming") == []
    assert storage.list_reminders("completed")[0]["id"] == created["id"]
    assert database.exists()


def test_upcoming_overdue_and_all_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFEADMIN_DB_PATH", str(tmp_path / "reminders.sqlite3"))
    today = date.today()
    overdue = storage.add_reminder("Pay bill", (today - timedelta(days=1)).isoformat())
    upcoming = storage.add_reminder("Appointment", today.isoformat())

    assert [item["id"] for item in storage.list_reminders("overdue")] == [overdue["id"]]
    assert [item["id"] for item in storage.list_reminders("upcoming")] == [upcoming["id"]]
    assert {item["id"] for item in storage.list_reminders("all")} == {
        overdue["id"],
        upcoming["id"],
    }


def test_find_reminders_is_case_insensitive_and_limited(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFEADMIN_DB_PATH", str(tmp_path / "reminders.sqlite3"))
    matching = storage.add_reminder("Dentist appointment", "2030-05-10")
    storage.add_reminder("Pay electricity bill", "2030-05-15")

    results = storage.find_reminders("DENTIST")

    assert [item["id"] for item in results] == [matching["id"]]
    with pytest.raises(ValueError, match="query must contain"):
        storage.find_reminders(" ")


@pytest.mark.parametrize(
    ("title", "due_date", "due_time"),
    [
        (" ", "2030-11-10", None),
        ("valid title", "2030-02-30", None),
        ("valid title", "2030-11-10", "25:00"),
        ("valid title", "2030-11-10", "09:30+02:00"),
        ("valid title", "2030-11-10", "930"),
    ],
)
def test_invalid_reminder_data_is_rejected(tmp_path, monkeypatch, title, due_date, due_time):
    monkeypatch.setenv("LIFEADMIN_DB_PATH", str(tmp_path / "reminders.sqlite3"))
    with pytest.raises(ValueError):
        storage.add_reminder(title, due_date, due_time)


def test_missing_reminder_and_empty_update_are_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFEADMIN_DB_PATH", str(tmp_path / "reminders.sqlite3"))
    with pytest.raises(ValueError, match="provide at least one field"):
        storage.update_reminder("missing-id")
    with pytest.raises(ValueError, match="reminder not found"):
        storage.mark_completed("missing-id")
    reminder = storage.add_reminder("Meeting", "2030-11-10", due_time="09:30")
    with pytest.raises(ValueError, match="not both"):
        storage.update_reminder(
            reminder["id"],
            due_time="10:00",
            clear_due_time=True,
        )


def test_title_based_changes_require_a_unique_match(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFEADMIN_DB_PATH", str(tmp_path / "reminders.sqlite3"))
    first = storage.add_reminder("Dentist checkup", "2030-05-10")
    second = storage.add_reminder("Dentist cleaning", "2030-05-12")

    with pytest.raises(ValueError, match="multiple reminders match"):
        storage.mark_completed(match_title="dentist")
    assert storage.list_reminders("all")[0]["status"] == "open"

    updated = storage.update_reminder(
        match_title="Dentist checkup",
        due_date="2030-05-11",
    )
    assert updated["id"] == first["id"]
    assert updated["due_date"] == "2030-05-11"

    completed = storage.mark_completed(match_title="cleaning")
    assert completed["id"] == second["id"]
    assert completed["status"] == "completed"


def test_current_date_includes_timezone():
    result = storage.get_current_date()
    assert result["current_date"] == date.today().isoformat()
    assert result["timezone"]
