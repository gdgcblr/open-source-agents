import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def test_all_five_tools_through_real_stdio_client(tmp_path):
    async def run():
        source_root = str(Path(__file__).resolve().parents[1])
        # Explicit import path permits this source test from an unrelated working directory.
        # Distribution verification separately runs an installed wheel with no PYTHONPATH.
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "pulseblr_events_mcp",
                "--source",
                "sample",
                "--now",
                "2026-10-24T08:00:00+05:30",
            ],
            env={"PATH": os.defpath, "PYTHONPATH": source_root},
            cwd=tmp_path,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=20) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert {tool.name for tool in tools.tools} == {
                    "search_events",
                    "get_event",
                    "list_topics",
                    "recommend_communities",
                    "plan_schedule",
                }
                result = await session.call_tool("search_events", {"when": "weekend", "limit": 10})
                assert not result.is_error
                payload = result.structured_content
                assert payload["data_mode"] == "sample" and payload["events"]
                ids = [event["id"] for event in payload["events"]]
                cases = [
                    ("get_event", {"event_id": ids[0]}),
                    ("list_topics", {"when": "weekend"}),
                    ("recommend_communities", {"event_ids": ids[:10], "interests": ["AI"]}),
                    ("plan_schedule", {"event_ids": ids[:10], "max_events": 2}),
                ]
                for name, arguments in cases:
                    result = await session.call_tool(name, arguments)
                    assert not result.is_error, (name, result)
                    assert result.structured_content["data_mode"] == "sample"
                    assert "Fictional" in " ".join(result.structured_content["warnings"])
                bad = await session.call_tool("plan_schedule", {"max_events": 99})
                assert bad.is_error
                no_results = await session.call_tool("search_events", {"query": "zzzznomatches"})
                assert not no_results.is_error and no_results.structured_content["events"] == []

    asyncio.run(run())
