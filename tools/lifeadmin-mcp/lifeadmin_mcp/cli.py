"""Command-line interface for everyday LifeAdmin reminder management."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date
from typing import Sequence

from lifeadmin_mcp import storage


def _format_reminder(reminder: dict[str, str | None]) -> str:
    due = reminder["due_date"]
    if reminder["due_time"]:
        due = f"{due} {reminder['due_time']}"
    category = f" [{reminder['category']}]" if reminder["category"] else ""
    return f"{due}  {reminder['title']}{category}  ({reminder['status']}; {reminder['id']})"


def _print_reminders(reminders: list[dict[str, str | None]], empty_message: str) -> None:
    if not reminders:
        print(empty_message)
        return
    for reminder in reminders:
        print(_format_reminder(reminder))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lifeadmin",
        description="Manage your personal reminders stored in a local SQLite database.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="Add a reminder.")
    add.add_argument("title", help="Short description of the task.")
    add.add_argument("--due", required=True, help="Due date in YYYY-MM-DD format.")
    add.add_argument("--time", dest="due_time", help="Optional local time in HH:MM format.")
    add.add_argument("--category", help="Optional category, e.g. bills or appointments.")
    add.add_argument("--notes", help="Optional notes.")

    list_command = commands.add_parser("list", help="List saved reminders.")
    list_command.add_argument(
        "--status",
        choices=("upcoming", "overdue", "completed", "all"),
        default="upcoming",
    )
    list_command.add_argument("--limit", type=int, default=50)

    today = commands.add_parser("today", help="Show overdue reminders and those due today.")
    today.add_argument("--date", help="Override today's date (YYYY-MM-DD), useful for testing.")

    find = commands.add_parser("find", help="Search reminder titles.")
    find.add_argument("query")

    complete = commands.add_parser("complete", help="Complete one reminder by ID or title.")
    identity = complete.add_mutually_exclusive_group(required=True)
    identity.add_argument("--id", dest="reminder_id", help="Reminder ID shown by lifeadmin list.")
    identity.add_argument("--title", dest="match_title", help="Unique text from its title.")

    update = commands.add_parser("update", help="Update one reminder by ID or unique title.")
    identity = update.add_mutually_exclusive_group(required=True)
    identity.add_argument("--id", dest="reminder_id", help="Reminder ID shown by lifeadmin list.")
    identity.add_argument("--title", dest="match_title", help="Unique text from its title.")
    update.add_argument("--due", dest="due_date", help="New due date in YYYY-MM-DD format.")
    update.add_argument("--time", dest="due_time", help="New local time in HH:MM format.")
    update.add_argument("--clear-time", action="store_true", help="Remove the reminder time.")
    update.add_argument("--category", help="Set category; use an empty value to clear it.")
    update.add_argument("--notes", help="Set notes; use an empty value to clear them.")

    return parser


def _run(args: argparse.Namespace) -> None:
    if args.command == "add":
        reminder = storage.add_reminder(
            args.title,
            args.due,
            due_time=args.due_time,
            category=args.category,
            notes=args.notes,
        )
        print(f"Saved reminder: {_format_reminder(reminder)}")
    elif args.command == "list":
        _print_reminders(
            storage.list_reminders(args.status, args.limit),
            f"No {args.status} reminders.",
        )
    elif args.command == "today":
        current_date = args.date or date.today().isoformat()
        overdue = storage.list_reminders("overdue", as_of_date=current_date)
        due_today = [
            reminder
            for reminder in storage.list_reminders("upcoming", as_of_date=current_date)
            if reminder["due_date"] == current_date
        ]
        print(f"LifeAdmin for {current_date}")
        print("\nOverdue")
        _print_reminders(overdue, "  Nothing overdue.")
        print("\nDue today")
        _print_reminders(due_today, "  Nothing due today.")
    elif args.command == "find":
        _print_reminders(storage.find_reminders(args.query), "No matching reminders.")
    elif args.command == "complete":
        reminder = storage.mark_completed(args.reminder_id, args.match_title)
        print(f"Completed: {_format_reminder(reminder)}")
    elif args.command == "update":
        if args.clear_time and args.due_time is not None:
            raise ValueError("choose --time or --clear-time, not both")
        reminder = storage.update_reminder(
            args.reminder_id,
            due_date=args.due_date,
            due_time=args.due_time,
            clear_due_time=args.clear_time,
            category=args.category,
            notes=args.notes,
            match_title=args.match_title,
        )
        print(f"Updated reminder: {_format_reminder(reminder)}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        _run(args)
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"lifeadmin: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
