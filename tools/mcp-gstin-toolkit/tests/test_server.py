"""End-to-end check: start the server over stdio and talk to it as an MCP client would."""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SAMPLE = Path(__file__).parent.parent / "examples" / "sample_feed.csv"


async def _session_checks():
    params = StdioServerParameters(command=sys.executable, args=["-m", "gstin_toolkit.server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = {t.name for t in (await session.list_tools()).tools}
            assert tools == {"validate_gstin", "validate_gstins", "lookup_state", "audit_csv"}

            result = await session.call_tool("audit_csv", {"path": str(SAMPLE)})
            assert json.loads(result.content[0].text)["summary"]["rows_with_issues"] == 7

            prompts = {p.name for p in (await session.list_prompts()).prompts}
            assert prompts == {"review_gst_feed"}
            prompt = await session.get_prompt("review_gst_feed", {"path": "@" + str(SAMPLE), "recipient": "Ops"})
            text = prompt.messages[0].content.text
            assert f"at: {SAMPLE}\n" in text and "audit_csv" in text and "Ops" in text


def test_server_over_stdio():
    asyncio.run(asyncio.wait_for(_session_checks(), 60))
