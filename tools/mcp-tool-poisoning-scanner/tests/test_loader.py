import pytest

from mcp_poison_scan.loader import LoadError, expand, server_spec


def test_stdio_entry():
    assert server_spec({"command": "npx", "args": ["-y", "pkg"], "env": {"A": "1"}}) == \
        ("stdio", ["npx", "-y", "pkg"], {"A": "1"})


@pytest.mark.parametrize("spec", [
    {"type": "http", "url": "https://x.example/mcp"},              # VS Code / Claude Code
    {"url": "https://x.example/mcp"},                              # Cursor
    {"serverUrl": "https://x.example/mcp"},                        # Windsurf
    {"transport": "streamable-http", "url": "https://x.example/mcp"},
])
def test_remote_entries(spec):
    assert server_spec(spec) == ("http", "https://x.example/mcp", {})


def test_legacy_sse_is_unsupported():
    kind, reason, _ = server_spec({"type": "sse", "url": "https://x.example/sse"})
    assert kind == "unsupported" and "SSE" in reason


def test_expands_environment_variables(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "abc")
    assert expand({"Authorization": "Bearer ${env:MY_TOKEN}", "X": "${MY_TOKEN}"}) == \
        {"Authorization": "Bearer abc", "X": "abc"}


def test_unresolved_variables_raise(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    with pytest.raises(LoadError, match=r"\$\{input:token\}"):
        expand("Bearer ${input:token}")
    with pytest.raises(LoadError, match="MISSING_VAR"):
        expand("${env:MISSING_VAR}")
