import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_mcp_stdio_exposes_and_runs_reminder_tools(tmp_path):
    async def exercise_server():
        env = {**os.environ, "LIFEADMIN_DB_PATH": str(tmp_path / "mcp.sqlite3")}
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "lifeadmin_mcp.server"],
            env=env,
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tool_list = await session.list_tools()
                tool_names = {tool.name for tool in tool_list.tools}
                assert {
                    "add_reminder",
                    "list_reminders",
                    "find_reminders",
                    "update_reminder",
                    "mark_completed",
                    "get_current_date",
                } <= tool_names

                result = await session.call_tool(
                    "add_reminder",
                    {"title": "Renew insurance", "due_date": "2030-11-10"},
                )
                assert not result.isError
                saved = result.structuredContent
                assert saved["title"] == "Renew insurance"

                listing = await session.call_tool(
                    "list_reminders", {"status": "upcoming"}
                )
                assert not listing.isError
                reminders = listing.structuredContent["result"]
                assert reminders[0]["id"] == saved["id"]

                updated = await session.call_tool(
                    "update_reminder",
                    {"match_title": "Renew insurance", "due_time": "09:30"},
                )
                assert not updated.isError
                cleared = await session.call_tool(
                    "update_reminder",
                    {"reminder_id": saved["id"], "clear_due_time": True},
                )
                assert not cleared.isError
                assert cleared.structuredContent["due_time"] is None

    asyncio.run(exercise_server())
