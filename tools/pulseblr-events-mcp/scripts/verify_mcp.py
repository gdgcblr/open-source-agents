"""Verify all five tools through an actual stdio MCP session, without an LLM or API key."""

import argparse
import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

EXPECTED_TOOLS = {
    "search_events",
    "get_event",
    "list_topics",
    "recommend_communities",
    "plan_schedule",
}


async def verify(source):
    args = ["-m", "pulseblr_events_mcp", "--source", source]
    if source == "sample":
        args.extend(["--now", "2026-10-24T08:00:00+05:30"])
    params = StdioServerParameters(command=sys.executable, args=args)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=120) as session:
            initialized = await session.initialize()
            listing = await session.list_tools()
            names = {tool.name for tool in listing.tools}
            if names != EXPECTED_TOOLS:
                raise RuntimeError("The server must advertise exactly the five documented tools.")

            async def call(name, arguments):
                result = await session.call_tool(name, arguments, read_timeout_seconds=120)
                if result.is_error or not isinstance(result.structured_content, dict):
                    raise RuntimeError(f"{name} did not return a successful structured result.")
                payload = result.structured_content
                if payload.get("data_mode") != source:
                    raise RuntimeError("The tool returned the wrong data-mode label.")
                if source == "sample" and not any(
                    "fictional" in str(w).casefold() for w in payload.get("warnings", [])
                ):
                    raise RuntimeError("A sample result omitted its fictional-data warning.")
                return payload

            topics = await call("list_topics", {"when": "weekend"})
            search = await call("search_events", {"when": "weekend", "limit": 10})
            ids = [event["id"] for event in search["events"]]
            if ids:
                detail = await call("get_event", {"event_id": ids[0]})
                communities = await call(
                    "recommend_communities",
                    {
                        "event_ids": ids[:10],
                        "interests": ["AI", "Open Source"],
                        "limit": 3,
                    },
                )
                schedule = await call(
                    "plan_schedule",
                    {
                        "event_ids": ids[:10],
                        "interests": ["AI", "Open Source"],
                        "max_events": 2,
                        "transfer_buffer_minutes": 60,
                    },
                )
                if not detail["found"]:
                    raise RuntimeError("The first search result could not be resolved.")
            else:
                # Empty live calendars are valid. The known-absent ID exercises get_event safely.
                detail = await call("get_event", {"event_id": "000000000000000000000000"})
                communities = await call("recommend_communities", {"when": "weekend"})
                schedule = await call("plan_schedule", {"when": "weekend"})

            empty = await call("search_events", {"query": "zzzznomatchesmcpverification"})
            if empty["events"]:
                raise RuntimeError("The no-match verification unexpectedly returned events.")
            invalid = await session.call_tool("plan_schedule", {"max_events": 99})
            if not invalid.is_error:
                raise RuntimeError("An invalid event cap was accepted.")
            return {
                "source": source,
                "protocol_version": initialized.protocol_version,
                "tools_verified": sorted(names),
                "returned_events": len(ids),
                "supported_topics": len(topics["supported_topics"]),
                "communities": [group["organizer"] for group in communities["communities"]],
                "selected_ids": [entry["event"]["id"] for entry in schedule["selected"]],
                "needs_duration_ids": [
                    entry["event"]["id"] for entry in schedule["needs_duration"]
                ],
                "conditional_on_assumptions": schedule["conditional_on_assumptions"],
                "no_match_case": "passed",
                "invalid_argument_case": "passed",
                "warnings": schedule["warnings"],
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("sample", "live"), default="sample")
    args = parser.parse_args()
    try:
        result = asyncio.run(verify(args.source))
    except Exception:
        print(
            "MCP verification failed. Check installation and source availability; no raw errors are printed.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
