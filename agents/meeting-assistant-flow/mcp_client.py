"""Call the actual MCP subprocess; only anonymous intervals cross this boundary."""

import asyncio
import json
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def get_slots(meeting: dict, busy: list[dict]) -> list[dict]:
    params = StdioServerParameters(command=sys.executable,
                                   args=[str(Path(__file__).with_name("mcp_server.py"))], env={})
    arguments = {"date_from": meeting["date_from"], "date_to": meeting["date_to"],
                 "timezone_name": meeting["timezone"], "duration_minutes": meeting["duration"],
                 "hour_start": meeting["hour_start"], "hour_end": meeting["hour_end"], "busy": busy,
                 "include_weekends": meeting.get("include_weekends", False)}
    async with asyncio.timeout(30):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                result = await client.call_tool("find_slots", arguments)
                if result.isError:
                    raise ValueError("Availability calculation failed. Review the date range and working hours.")
                for block in result.content:
                    if block.type == "text":
                        return json.loads(block.text)["slots"]
    raise ValueError("The availability tool returned no result.")
