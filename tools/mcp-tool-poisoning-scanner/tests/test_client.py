import sys

import pytest

from mcp_poison_scan.client import McpClientError, list_tools


def test_lists_all_tools_following_pagination(fake_server_cmd):
    tools = list_tools(fake_server_cmd, timeout=10)
    assert [t["name"] for t in tools] == ["add", "get_weather", "send_email"]


def test_poisoned_mode(fake_server_cmd):
    tools = list_tools(fake_server_cmd, env={"FAKE_MCP_MODE": "poisoned"}, timeout=10)
    assert "daily_fact" in [t["name"] for t in tools]


def test_accepts_command_string(fake_server_cmd):
    cmd = " ".join(f'"{part}"' for part in fake_server_cmd)
    assert len(list_tools(cmd, timeout=10)) == 3


def test_missing_executable_raises():
    with pytest.raises(McpClientError):
        list_tools(["definitely-not-a-real-binary-xyz"], timeout=5)


def test_server_that_exits_raises():
    with pytest.raises(McpClientError):
        list_tools([sys.executable, "-c", "pass"], timeout=5)


def test_silent_server_times_out():
    with pytest.raises(McpClientError, match="Timed out"):
        list_tools([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1)
