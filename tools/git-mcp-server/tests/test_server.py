"""
Unit tests for git-mcp-server protocol handling and tool execution.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import server


class TestGitMcpServer(unittest.TestCase):

    def test_initialize(self):
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        }
        res = server.handle_jsonrpc_message(req)
        self.assertEqual(res["id"], 1)
        self.assertEqual(res["result"]["serverInfo"]["name"], "git-mcp-server")
        self.assertIn("tools", res["result"]["capabilities"])

    def test_tools_list(self):
        req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        res = server.handle_jsonrpc_message(req)
        tool_names = [t["name"] for t in res["result"]["tools"]]
        self.assertIn("git_status", tool_names)
        self.assertIn("git_diff", tool_names)
        self.assertIn("git_log", tool_names)
        self.assertIn("git_branches", tool_names)
        self.assertIn("git_show", tool_names)

    def test_tools_call_status(self):
        req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "git_status", "arguments": {"repo_path": "."}},
        }
        res = server.handle_jsonrpc_message(req)
        content = res["result"]["content"][0]["text"]
        self.assertTrue(len(content) > 0)

    def test_tools_call_branches(self):
        req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "git_branches", "arguments": {}},
        }
        res = server.handle_jsonrpc_message(req)
        content = res["result"]["content"][0]["text"]
        self.assertIn("feat/git-commit-agent", content)

    def test_unknown_method(self):
        req = {"jsonrpc": "2.0", "id": 99, "method": "non_existent_method"}
        res = server.handle_jsonrpc_message(req)
        self.assertEqual(res["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
