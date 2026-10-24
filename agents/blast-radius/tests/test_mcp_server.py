"""Unit tests for Model Context Protocol (MCP) Server."""

import unittest
from pathlib import Path
from blast_radius.mcp_server import MCPServer

FIXTURE_REPO = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"
DIFF_FILE = Path(__file__).resolve().parent.parent / "fixtures" / "changes" / "payment_logic_update.diff"


class TestMCPServer(unittest.TestCase):

    def setUp(self):
        self.server = MCPServer()

    def test_initialize(self):
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {}
        }
        res = self.server.handle_request(req)
        self.assertEqual(res["id"], 1)
        self.assertEqual(res["result"]["serverInfo"]["name"], "blast-radius-mcp")
        self.assertIn("tools", res["result"]["capabilities"])

    def test_tools_list(self):
        req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        res = self.server.handle_request(req)
        tool_names = [t["name"] for t in res["result"]["tools"]]
        self.assertIn("analyze_change_impact", tool_names)
        self.assertIn("find_method_callers", tool_names)
        self.assertIn("recommend_test_targets", tool_names)

    def test_tools_call_find_callers(self):
        req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "find_method_callers",
                "arguments": {
                    "method_name": "processPayment",
                    "repo_path": str(FIXTURE_REPO)
                }
            }
        }
        res = self.server.handle_request(req)
        self.assertEqual(res["id"], 3)
        content_text = res["result"]["content"][0]["text"]
        self.assertIn("OrderService#createOrder", content_text)

    def test_tools_call_analyze_impact(self):
        diff_text = DIFF_FILE.read_text(encoding="utf-8")
        req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "analyze_change_impact",
                "arguments": {
                    "diff": diff_text,
                    "repo_path": str(FIXTURE_REPO)
                }
            }
        }
        res = self.server.handle_request(req)
        self.assertEqual(res["id"], 4)
        content_text = res["result"]["content"][0]["text"]
        self.assertIn("BlastRadius: Change Impact Analysis Report", content_text)
        self.assertIn("HIGH RISK", content_text)


if __name__ == "__main__":
    unittest.main()

