"""LifeAdmin MCP server using stdio transport."""

from typing import Literal

from mcp.server.fastmcp import FastMCP

from lifeadmin_mcp import storage

mcp = FastMCP("LifeAdmin")


@mcp.tool()
def add_reminder(
    title: str,
    due_date: str,
    due_time: str | None = None,
    category: str | None = None,
    notes: str | None = None,
) -> dict[str, str | None]:
    """Save a personal deadline. Use YYYY-MM-DD; ask if the intended date is unclear."""
    return storage.add_reminder(title, due_date, due_time, category, notes)


@mcp.tool()
def list_reminders(
    status: Literal["upcoming", "overdue", "completed", "all"] = "upcoming",
    limit: int = 50,
) -> list[dict[str, str | None]]:
    """List saved reminders; upcoming means open reminders due today or later."""
    return storage.list_reminders(status, limit)


@mcp.tool()
def find_reminders(query: str, limit: int = 20) -> list[dict[str, str | None]]:
    """Find reminders by case-insensitive title text before editing or completing one."""
    return storage.find_reminders(query, limit)


@mcp.tool()
def update_reminder(
    reminder_id: str | None = None,
    title: str | None = None,
    due_date: str | None = None,
    due_time: str | None = None,
    category: str | None = None,
    notes: str | None = None,
    clear_due_time: bool = False,
    match_title: str | None = None,
) -> dict[str, str | None]:
    """Edit one reminder by ID or a unique match_title; clear its time with clear_due_time."""
    return storage.update_reminder(
        reminder_id,
        title=title,
        due_date=due_date,
        due_time=due_time,
        category=category,
        notes=notes,
        clear_due_time=clear_due_time,
        match_title=match_title,
    )


@mcp.tool()
def mark_completed(
    reminder_id: str | None = None,
    match_title: str | None = None,
) -> dict[str, str | None]:
    """Complete one reminder by ID or a unique match_title; ambiguous matches are rejected."""
    return storage.mark_completed(reminder_id, match_title)


@mcp.tool()
def get_current_date() -> dict[str, str]:
    """Get the host's local calendar date and timezone before interpreting relative dates."""
    return storage.get_current_date()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
