"""Claude Code plugin packaging: manifest, marketplace, hook and MCP config, and the zero-install launcher."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(rel):
    return json.loads((ROOT / rel).read_text())


def test_manifest_and_marketplace_agree():
    plugin = load(".claude-plugin/plugin.json")
    market = load(".claude-plugin/marketplace.json")
    assert plugin["name"] == "prompt-enhancer" and plugin["version"]
    entry = market["plugins"][0]
    assert entry["name"] == plugin["name"] and entry["source"] == "./" and market["owner"]["name"]


def test_versions_match_package():
    from prompt_enhancer import __version__
    assert load(".claude-plugin/plugin.json")["version"] == __version__
    assert f'version = "{__version__}"' in (ROOT / "pyproject.toml").read_text()


def test_hook_uses_exec_form_with_plugin_root():
    h = load("hooks/hooks.json")["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert h["type"] == "command" and h["command"] == "python3"
    assert h["args"][0] == "${CLAUDE_PLUGIN_ROOT}/scripts/run.py" and h["args"][1:] == ["hook", "claude-code"]


def test_mcp_config_points_at_launcher():
    s = load(".mcp.json")["mcpServers"]["prompt-enhancer"]
    assert s["command"] == "python3" and s["args"] == ["${CLAUDE_PLUGIN_ROOT}/scripts/run.py", "mcp"]
    assert s["env"]["PROMPT_ENHANCER_MODEL"] == "claude"  # plugin runs inside Claude Code


def test_skills_have_descriptions():
    for name in ("enhance", "check"):
        text = (ROOT / "skills" / name / "SKILL.md").read_text()
        assert text.startswith("---\ndescription: ") and "$ARGUMENTS" in text


def _run_hook(payload, extra_env=None):
    # Exactly what Claude Code runs, with ${CLAUDE_PLUGIN_ROOT} substituted; no install, system Python, no PYTHONPATH.
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PROMPT_ENHANCER_MODEL", "ANTHROPIC_MODEL"}}
    env.update(extra_env or {})
    args = [a.replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT)) for a in load("hooks/hooks.json")["hooks"]["UserPromptSubmit"][0]["hooks"][0]["args"]]
    return subprocess.run([sys.executable, *args], input=json.dumps(payload), capture_output=True, text=True, timeout=30, env=env)


def test_launcher_runs_hook_without_install():
    p = _run_hook({"hook_event_name": "UserPromptSubmit", "prompt": "Refactor the cache. Keep the public API unchanged."},
                  {"PROMPT_ENHANCER_RESTATE": "1"})
    assert p.returncode == 0
    out = json.loads(p.stdout)
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "Keep the public API unchanged." in out["hookSpecificOutput"]["additionalContext"]


def test_launcher_hook_fails_open_on_garbage():
    p = _run_hook("not even an object")
    assert p.returncode == 0 and p.stdout == ""


def test_mcp_server_uses_claude_profile_from_plugin_env():
    req = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
           "params": {"name": "analyze_prompt", "arguments": {"prompt": "Write a CLI tool that converts CSV files to JSON."}}}
    env = {**os.environ, **load(".mcp.json")["mcpServers"]["prompt-enhancer"]["env"]}
    env.pop("PYTHONPATH", None)
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "run.py"), "mcp"], input=json.dumps(req) + "\n",
                       capture_output=True, text=True, timeout=30, env=env)
    assert json.loads(p.stdout)["result"]["structuredContent"]["model_profile"] == "anthropic-claude"
