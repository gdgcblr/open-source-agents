import asyncio
import json
import sys
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class McpProtocolIntegrationTest(unittest.TestCase):
    def test_server_discovers_tools_and_handles_real_stdio_call(self):
        async def exercise():
            project_root = Path(__file__).parents[1]
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "build_doctor_mcp.server"],
                cwd=project_root,
                env={"PYTHONPATH": str(project_root / "src")},
            )
            async with stdio_client(parameters) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    names = {tool.name for tool in tools.tools}
                    result = await session.call_tool(
                        "analyze_failure", {"log": "error: cannot find symbol"}
                    )
                    return names, json.loads(result.content[0].text)

        names, result = asyncio.run(exercise())
        self.assertIn("analyze_failure", names)
        self.assertIn("inspect_project", names)
        self.assertIn("verify_resolution", names)
        self.assertEqual("compilation", result["failure_type"])
        self.assertEqual("1.1", result["schema_version"])

    def test_unavailable_server_fails_initialization(self):
        async def exercise_failure():
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-c", "raise SystemExit(7)"],
            )
            async with stdio_client(parameters) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()

        with self.assertRaises(Exception):
            asyncio.run(exercise_failure())


if __name__ == "__main__":
    unittest.main()
