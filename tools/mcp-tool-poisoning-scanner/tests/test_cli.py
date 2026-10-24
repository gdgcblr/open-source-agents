import json
import sys

from conftest import FAKE_SERVER, FIXTURES
from mcp_poison_scan.cli import main


def test_scan_benign_file_exits_zero(capsys):
    assert main(["scan", "--file", str(FIXTURES / "benign_tools.json")]) == 0
    assert "No findings" in capsys.readouterr().out


def test_scan_poisoned_file_exits_one(capsys):
    assert main(["scan", "--file", str(FIXTURES / "poisoned_tools.json")]) == 1
    out = capsys.readouterr().out
    assert "HIDDEN_UNICODE" in out and "Ignore previous instructions" in out


def test_fail_on_threshold(tmp_path):
    long_tool = tmp_path / "long.json"
    long_tool.write_text(json.dumps([{"name": "x", "description": "a " * 600}]))
    assert main(["scan", "--file", str(long_tool), "--fail-on", "medium"]) == 0
    assert main(["scan", "--file", str(long_tool), "--fail-on", "low"]) == 1


def test_json_output_is_valid(capsys):
    main(["scan", "--file", str(FIXTURES / "poisoned_tools.json"), "--format", "json"])
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["high"] > 0
    assert {"rule_id", "severity", "server", "tool", "path", "message", "evidence"} <= set(report["findings"][0])


def test_scan_live_server(capsys, fake_server_cmd, monkeypatch):
    monkeypatch.setenv("FAKE_MCP_MODE", "poisoned")
    assert main(["scan", "--server", " ".join(f'"{p}"' for p in fake_server_cmd)]) == 1


def test_pin_then_detect_rug_pull(tmp_path, capsys, fake_server_cmd, monkeypatch):
    lock = tmp_path / "mcp-tools.lock.json"
    server = " ".join(f'"{p}"' for p in fake_server_cmd)
    monkeypatch.setenv("FAKE_MCP_MODE", "benign")
    assert main(["pin", "--server", server, "--name", "weather", "--out", str(lock)]) == 0
    assert main(["scan", "--server", server, "--name", "weather", "--lock", str(lock)]) == 0
    monkeypatch.setenv("FAKE_MCP_MODE", "rugpull")
    capsys.readouterr()
    assert main(["scan", "--server", server, "--name", "weather", "--lock", str(lock)]) == 1
    assert "RUG_PULL" in capsys.readouterr().out


def test_config_without_launch_lists_servers(capsys):
    assert main(["scan", "--config", str(FIXTURES / "sample_mcp_config.json")]) == 0
    out = capsys.readouterr().out
    assert "weather" in out and "remote-docs" in out and "--launch" in out
    assert "No findings" not in out


def test_config_with_launch_scans_stdio_and_remote_servers(tmp_path, capsys, monkeypatch, http_server):
    monkeypatch.setenv("FAKE_MCP_MODE", "poisoned")
    monkeypatch.setenv("FAKE_TOKEN", "t0k")
    url = http_server(mode="benign", token="t0k")
    config = tmp_path / "mcp.json"
    # VS Code style: top-level "servers", env-var expansion in headers.
    config.write_text(json.dumps({"servers": {
        "weather": {"type": "stdio", "command": sys.executable, "args": [str(FAKE_SERVER)]},
        "remote": {"type": "http", "url": url + "/mcp", "headers": {"Authorization": "Bearer ${env:FAKE_TOKEN}"}},
    }}))
    assert main(["scan", "--config", str(config), "--launch"]) == 1
    out = capsys.readouterr().out
    assert "daily_fact" in out
    assert "Scanned 3 tool(s) from remote" in out


def test_config_unresolved_input_variable_is_reported(tmp_path, capsys):
    config = tmp_path / "mcp.json"
    config.write_text(json.dumps({"servers": {
        "remote": {"type": "http", "url": "http://127.0.0.1:9/mcp", "headers": {"Authorization": "Bearer ${input:token}"}},
    }}))
    assert main(["scan", "--config", str(config), "--launch"]) == 2
    out = capsys.readouterr().out
    assert "${input:token}" in out and "No findings" not in out


def test_scan_url_with_header(capsys, http_server):
    url = http_server(mode="poisoned", token="abc")
    assert main(["scan", "--url", url + "/mcp", "--header", "Authorization: Bearer abc"]) == 1
    assert "HIDDEN_UNICODE" in capsys.readouterr().out


def test_url_without_auth_exits_two(capsys, http_server):
    url = http_server(token="abc")
    assert main(["scan", "--url", url + "/mcp"]) == 2
    assert "--header" in capsys.readouterr().err


def test_header_requires_url():
    assert main(["scan", "--file", str(FIXTURES / "benign_tools.json"), "--header", "X: y"]) == 2


def test_bad_header_format_exits_two():
    assert main(["scan", "--url", "http://127.0.0.1:9/mcp", "--header", "no-colon"]) == 2


def test_pin_and_rug_pull_over_http(tmp_path, capsys, http_server):
    lock = tmp_path / "lock.json"
    benign = http_server(mode="benign")
    rugpull = http_server(mode="rugpull")
    assert main(["pin", "--url", benign + "/mcp", "--name", "srv", "--out", str(lock)]) == 0
    assert main(["scan", "--url", rugpull + "/mcp", "--name", "srv", "--lock", str(lock)]) == 1
    assert "RUG_PULL" in capsys.readouterr().out


def test_missing_file_exits_two(capsys):
    assert main(["scan", "--file", "does-not-exist.json"]) == 2
