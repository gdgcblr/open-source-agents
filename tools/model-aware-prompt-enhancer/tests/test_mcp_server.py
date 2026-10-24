"""MCP server: legacy (initialize) and modern (per-request _meta) clients, tools, errors, stdio framing."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

from prompt_enhancer.mcp_server import MODERN_VERSIONS, TOOLS, Server, serve

ROOT = Path(__file__).resolve().parents[1]
META = {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientInfo": {"name": "t", "version": "1"}}}
P = "Write a function that removes duplicate users. Keep it under 30 lines and do not use pandas."


def call(server, method, params=None, id=1):
    msg = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        msg["params"] = params
    return server.handle(msg)


def test_legacy_handshake_and_tools():
    s = Server()
    init = call(s, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "c", "version": "1"}})["result"]
    assert init["protocolVersion"] == "2025-06-18" and "tools" in init["capabilities"] and init["serverInfo"]["name"]
    assert s.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = call(s, "tools/list")["result"]
    assert "resultType" not in tools  # legacy shape
    assert [t["name"] for t in tools["tools"]] == ["analyze_prompt", "enhance_prompt", "resolve_model"]


def test_legacy_unknown_version_gets_latest_legacy():
    r = call(Server(), "initialize", {"protocolVersion": "1999-01-01"})["result"]
    assert r["protocolVersion"] == "2025-11-25"


def test_modern_discover_and_result_type():
    s = Server()
    d = call(s, "server/discover", META)["result"]
    assert d["resultType"] == "complete" and d["supportedVersions"] == MODERN_VERSIONS
    assert d["_meta"]["io.modelcontextprotocol/serverInfo"]["name"]
    assert call(s, "tools/list", META)["result"]["resultType"] == "complete"
    assert call(s, "ping", META)["result"] == {"resultType": "complete"}


def test_modern_unsupported_version_error():
    r = call(Server(), "tools/list", {"_meta": {"io.modelcontextprotocol/protocolVersion": "1900-01-01"}})
    assert r["error"]["code"] == -32022 and r["error"]["data"]["requested"] == "1900-01-01"
    assert "2026-07-28" in r["error"]["data"]["supported"]


def test_analyze_tool():
    r = call(Server(), "tools/call", {**META, "name": "analyze_prompt", "arguments": {"prompt": P, "model": "claude"}})["result"]
    assert r["isError"] is False and "PE401" in r["content"][0]["text"]
    assert any(d["rule_id"] == "PE401" for d in r["structuredContent"]["diagnostics"])


def test_enhance_tool_questions_answers_and_lock():
    s = Server()
    first = call(s, "tools/call", {"name": "enhance_prompt", "arguments": {"prompt": P, "model": "claude-sonnet-5"}})["result"]["structuredContent"]
    assert "PE401.1" in first["questions"] and first["lock_ok"]
    second = call(s, "tools/call", {"name": "enhance_prompt", "arguments": {"prompt": P, "model": "claude-sonnet-5", "answers": {"PE401": "Python 3.12"}}})["result"]
    data = second["structuredContent"]
    assert "Language/runtime: Python 3.12" in data["enhanced"] and data["lock_ok"] and data["diff"].startswith("--- original")
    assert "Keep it under 30 lines and do not use pandas." in data["enhanced"]


def test_resolve_tool():
    r = call(Server(), "tools/call", {"name": "resolve_model", "arguments": {"model": "claude-opus-4-6"}})["result"]["structuredContent"]
    assert r["profile"] == "anthropic-claude" and r["variant"] == "claude-opus-4.5-4.6"


def test_tool_input_errors():
    s = Server()
    assert call(s, "tools/call", {"name": "nope", "arguments": {}})["error"]["code"] == -32602
    assert call(s, "tools/call", {"name": "analyze_prompt", "arguments": {}})["error"]["code"] == -32602
    bad = call(s, "tools/call", {"name": "enhance_prompt", "arguments": {"prompt": "x", "accept": "PE1"}})["result"]
    assert bad["isError"] is True and "list of strings" in bad["content"][0]["text"]


def test_protocol_errors():
    s = Server()
    assert call(s, "does/not/exist")["error"]["code"] == -32601
    assert s.handle({"id": 1, "method": "x"})["error"]["code"] == -32600
    assert s.handle([1, 2])["error"]["code"] == -32600
    assert call(s, "tools/list", params=[1])["error"]["code"] == -32602


def test_tool_schemas_are_valid_objects():
    for t in TOOLS:
        assert t["inputSchema"]["type"] == "object" and t["annotations"]["readOnlyHint"] is True


def test_serve_framing_and_parse_errors():
    lines = "\n".join([
        "not json",
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        "",
        json.dumps({"jsonrpc": "2.0", "id": 7, "method": "ping"}),
    ]) + "\n"
    out = io.StringIO()
    assert serve(io.StringIO(lines), out) == 0
    msgs = [json.loads(line) for line in out.getvalue().splitlines()]
    assert msgs[0]["error"]["code"] == -32700 and msgs[1] == {"jsonrpc": "2.0", "id": 7, "result": {}}
    assert all("\n" not in line for line in out.getvalue().splitlines())


def test_stdio_subprocess_stdout_is_protocol_only_and_prompt_not_logged():
    secret = "PROJECT-NIGHTINGALE plan. Keep it under 50 words."
    reqs = [
        {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": META},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {**META, "name": "enhance_prompt", "arguments": {"prompt": secret}}},
    ]
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "run.py"), "mcp"], input="\n".join(json.dumps(r) for r in reqs) + "\n",
                       capture_output=True, text=True, timeout=30, env={**os.environ})
    assert p.returncode == 0 and "NIGHTINGALE" not in p.stderr
    out = [json.loads(line) for line in p.stdout.splitlines()]
    assert [m["id"] for m in out] == [1, 2] and out[1]["result"]["resultType"] == "complete"
