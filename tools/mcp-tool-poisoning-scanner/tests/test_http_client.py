import pytest

from mcp_poison_scan.client import McpClientError, list_tools_http


@pytest.mark.parametrize("response_format", ["json", "sse"])
def test_lists_tools_over_json_and_sse(http_server, response_format):
    url = http_server(response_format=response_format)
    tools = list_tools_http(url + "/mcp", timeout=5)
    assert [t["name"] for t in tools] == ["add", "get_weather", "send_email"]


def test_sends_auth_header(http_server):
    url = http_server(mode="poisoned", token="s3cret")
    tools = list_tools_http(url + "/mcp", headers={"Authorization": "Bearer s3cret"}, timeout=5)
    assert "daily_fact" in [t["name"] for t in tools]


def test_missing_auth_gives_helpful_error(http_server):
    url = http_server(token="s3cret")
    with pytest.raises(McpClientError, match=r"401.*--header"):
        list_tools_http(url + "/mcp", timeout=5)


def test_does_not_follow_redirects(http_server):
    url = http_server()
    with pytest.raises(McpClientError, match="redirect"):
        list_tools_http(url + "/redirect", headers={"Authorization": "Bearer x"}, timeout=5)


def test_rejects_non_http_urls():
    with pytest.raises(McpClientError, match="http"):
        list_tools_http("file:///etc/passwd", timeout=5)


def test_unreachable_server_raises():
    with pytest.raises(McpClientError, match="Could not connect"):
        list_tools_http("http://127.0.0.1:9/mcp", timeout=2)
