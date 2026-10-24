"""Regression tests for previously fixed bugs."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import SCRIPTED_CONFIG, proxy_client, read_jsonl
from helpers import scripted_cfg, scripted_matrix

from murphy.checks import build_checks
from murphy.cli import main
from murphy.config.schema import CheckConfig, PersonaConfig
from murphy.core.orchestrator import matrix_dir_for, run_budget, run_one
from murphy.replay import replay
from murphy.report.text import timeline
from murphy.targets import build_target
from murphy.targets.adk import AdkTarget
from murphy.users.scripted import ScriptedUser

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ENV_UPSTREAM = {"name": "env", "command": [sys.executable, str(FIXTURES / "env_server.py")], "cwd": str(FIXTURES)}


# 1. checks judge raw args; only persisted files are redacted
async def charge_twice_distinct(turn, message, call):
    await call("charge", {"order_id": "A1", "idempotency_token": "t-1"})
    await call("charge", {"order_id": "A1", "idempotency_token": "t-2"})
    return "charged"


async def test_checks_use_raw_args_and_persisted_trace_is_redacted(tmp_path):
    cfg = scripted_cfg()
    cfg.tools[0] = cfg.tools[0].model_validate(ENV_UPSTREAM)
    check = CheckConfig.model_validate({"id": "once-per-token", "type": "trace", "rule": "max_calls_per_key",
                                        "tool": "charge", "key": ["idempotency_token"], "max": 1, "label": "dup"})
    persona = PersonaConfig(id="p", goal="g")
    r = await run_one(cfg, persona, cfg.scenario("no-fault"), build_target(cfg.target, "test_regressions:charge_twice_distinct"),
                      ScriptedUser(["go"]), build_checks([check]), tmp_path / "run")
    assert {c["id"]: c["passed"] for c in r.checks}["once-per-token"] is True  # two distinct tokens: not a dup
    persisted = read_jsonl(tmp_path / "run" / "trace.jsonl") + read_jsonl(tmp_path / "run" / "tools.jsonl")
    assert all(e["args"]["idempotency_token"] == "***" for e in persisted if e["kind"] == "tool")


# 2. replay keeps the recorded seed
async def test_replay_uses_recorded_seed(tmp_path):
    cfg = scripted_cfg()
    cfg.seed = 42
    persona = cfg.personas[0]
    cell = tmp_path / "cooperative__timeout"
    await run_one(cfg, persona, cfg.scenario("timeout"), build_target(cfg.target), ScriptedUser(["return A12"]),
                  build_checks(cfg.checks), cell)
    fresh = scripted_cfg()  # seed 7, as a replay process would load it
    _, after, out = await replay(fresh, cell, build_target(fresh.target, "scripted_agents:fixed_policy"),
                                 build_checks(fresh.checks))
    assert after.seed == 42
    assert json.loads((out / "proxy.json").read_text())["seed"] == 42


# 3. replay without --target uses the recorded target
def test_cli_replay_defaults_to_recorded_target(tmp_path, capfd):  # sync: main() owns the event loop
    out = tmp_path / "runs"
    main(["run", "-c", str(SCRIPTED_CONFIG), "--out", str(out), "--faults", "timeout",
          "--target", "scripted_agents:fixed_policy"])
    cell = (out / "latest" / "cooperative__timeout").resolve()
    assert main(["replay", str(cell), "--policy", "monitor", "--no-fallback"]) == 0
    replayed = next(cell.parent.glob("cooperative__timeout__replay-*"))
    assert json.loads((replayed / "result.json").read_text())["target"] == "scripted_agents:fixed_policy"


# 5. AdkTarget.close stops the toolset even if the runner fails to close
async def test_adk_close_always_closes_toolset():
    class Runner:
        async def close(self):
            raise RuntimeError("runner cleanup failed")

    class Toolset:
        closed = False

        async def close(self):
            Toolset.closed = True

    target = AdkTarget(lambda toolset: None, label="t")
    target._runner, target._toolset = Runner(), Toolset()
    with pytest.raises(RuntimeError):
        await target.close()
    assert Toolset.closed and target._toolset is None


# 6. strictest budget wins
def test_run_budget_takes_strictest_rule():
    cfg = scripted_cfg()
    cfg.policy.rules = [*cfg.policy.rules, *(SimpleNamespace(type="budget", max_tool_calls=n) for n in (50, 10))]
    assert run_budget(cfg) == 10


# 7. upstreams inherit the caller's environment unless told not to
async def test_upstream_inherits_environment(run_dir, monkeypatch):
    monkeypatch.setenv("SL_DB_URL", "postgres://x")
    async with proxy_client(run_dir, upstreams=[ENV_UPSTREAM]) as c:
        inherited = await c.call_tool("getenv", {"name": "SL_DB_URL"})
    assert inherited.data["value"] == "postgres://x"
    async with proxy_client(run_dir, upstreams=[{**ENV_UPSTREAM, "inherit_env": False}]) as c:
        isolated = await c.call_tool("getenv", {"name": "SL_DB_URL"})
    assert isolated.data["value"] is None


# 8. report text has no tool-specific knowledge
def test_timeline_shows_all_args_generically():
    lines = timeline([{"kind": "tool", "tool": "escalate", "args": {"reason": "angry customer"}, "ok": True,
                       "upstream_called": True, "result": {"ticket": "T-9"}, "policy": {}}])
    assert "reason=angry customer" in lines[0] and '{"ticket":"T-9"}' in lines[0]


# 10. matrix dirs are unique even within the same second
def test_matrix_dirs_never_collide(tmp_path):
    cfg = scripted_cfg()
    names = {matrix_dir_for(tmp_path, cfg, "t", "monitor").name for _ in range(20)}
    assert len(names) == 20


async def test_run_matrix_refuses_non_empty_dir(tmp_path):
    (tmp_path / "leftover").mkdir()
    with pytest.raises(FileExistsError, match="not empty"):
        await scripted_matrix(tmp_path)


def test_replay_with_unloadable_recorded_target_explains_fix(tmp_path, capfd):
    out = tmp_path / "runs"
    main(["run", "-c", str(SCRIPTED_CONFIG), "--out", str(out), "--faults", "timeout"])
    cell = (out / "latest" / "cooperative__timeout").resolve()
    meta = json.loads((cell / "meta.json").read_text())
    meta["target"] = "renamed_module:naive_policy"
    (cell / "meta.json").write_text(json.dumps(meta))
    capfd.readouterr()
    assert main(["replay", str(cell), "--no-fallback"]) == 2
    assert "pass --target" in capfd.readouterr().err
