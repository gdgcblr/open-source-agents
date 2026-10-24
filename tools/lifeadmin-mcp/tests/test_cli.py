import pytest

from lifeadmin_mcp import cli
from lifeadmin_mcp import storage


def test_cli_add_today_update_and_complete(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LIFEADMIN_DB_PATH", str(tmp_path / "cli.sqlite3"))

    cli.main(["add", "Pay electricity bill", "--due", "2030-05-10", "--category", "bills"])
    assert "Saved reminder" in capsys.readouterr().out
    reminder_id = storage.list_reminders("all")[0]["id"]

    cli.main(["today", "--date", "2030-05-10"])
    today_output = capsys.readouterr().out
    assert "Pay electricity bill" in today_output
    assert "Due today" in today_output

    cli.main(["update", "--title", "electricity", "--due", "2030-05-11"])
    assert "2030-05-11" in capsys.readouterr().out

    cli.main(["complete", "--id", reminder_id])
    assert "Completed" in capsys.readouterr().out

    cli.main(["list", "--status", "completed"])
    assert "Pay electricity bill" in capsys.readouterr().out


def test_cli_today_shows_overdue_and_due_today(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LIFEADMIN_DB_PATH", str(tmp_path / "cli.sqlite3"))
    monkeypatch.setattr(
        "lifeadmin_mcp.cli.storage.list_reminders",
        lambda status, limit=50, as_of_date=None: {
            "overdue": [
                {
                    "due_date": "2030-05-09",
                    "due_time": None,
                    "title": "Late bill",
                    "category": None,
                    "status": "open",
                    "id": "late",
                }
            ],
            "upcoming": [
                {
                    "due_date": "2030-05-10",
                    "due_time": None,
                    "title": "Today task",
                    "category": None,
                    "status": "open",
                    "id": "today",
                }
            ],
        }[status],
    )

    cli.main(["today", "--date", "2030-05-10"])

    output = capsys.readouterr().out
    assert "Late bill" in output
    assert "Today task" in output


def test_cli_invalid_date_is_reported_without_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LIFEADMIN_DB_PATH", str(tmp_path / "cli.sqlite3"))

    with pytest.raises(SystemExit, match="2"):
        cli.main(["add", "Pay bill", "--due", "not-a-date"])

    assert "lifeadmin:" in capsys.readouterr().err


def test_cli_complete_refuses_ambiguous_title(tmp_path, monkeypatch, capsys):
    from lifeadmin_mcp import storage

    monkeypatch.setenv("LIFEADMIN_DB_PATH", str(tmp_path / "cli.sqlite3"))
    storage.add_reminder("Dentist checkup", "2030-05-10")
    storage.add_reminder("Dentist cleaning", "2030-05-12")

    with pytest.raises(SystemExit, match="2"):
        cli.main(["complete", "--title", "dentist"])

    assert "multiple reminders match" in capsys.readouterr().err
