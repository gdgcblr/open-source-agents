"""Runs persona x fault conversations: user ⇄ target, tools through the proxy, then checks."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from murphy.checks import Check, RunContext, run_checks
from murphy.config.schema import FaultScenario, PersonaConfig, PolicyMode, ProjectConfig
from murphy.core.trace import Recorder, write_json
from murphy.core.verdict import decide
from murphy.targets.base import Target, ToolEndpoint
from murphy.users.base import User

PROXY_MODULE = "murphy.proxy"


class RunResult(BaseModel):
    persona: str
    fault: str
    target: str
    policy_mode: PolicyMode
    seed: int
    passed: bool
    labels: list[str] = Field(default_factory=list)
    hint: str = ""
    end_reason: str
    turns: int = 0
    tool_calls: int = 0
    faults_fired: int = 0
    policy_violations: int = 0
    policy_blocks: int = 0
    checks: list[dict] = Field(default_factory=list)
    target_tokens: int = 0
    sim_tokens: int = 0
    wall_s: float = 0.0
    config_hash: str = ""
    replay_of: str | None = None
    replay_diverged: bool = False

    @property
    def verdict(self) -> str:
        return "PASS" if self.passed else "FAIL"

    @property
    def primary_label(self) -> str:
        return self.labels[0] if self.labels else ""


def config_hash(cfg: ProjectConfig) -> str:
    return hashlib.sha256(cfg.model_dump_json().encode()).hexdigest()[:12]


def run_budget(cfg: ProjectConfig) -> int:
    """Hard stop for a run: the strictest budget rule wins."""
    return min([r.max_tool_calls for r in cfg.policy.rules if r.type == "budget"], default=50)


def tool_endpoint(cfg: ProjectConfig, run_dir: Path, scenario: FaultScenario, policy_mode: PolicyMode,
                  seed: int) -> ToolEndpoint | None:
    if not cfg.tools:
        return None
    write_json(run_dir / "proxy.json", {
        "upstreams": [u.model_dump() for u in cfg.tools],
        "faults": [f.model_dump() for f in scenario.inject],
        "policy": {"mode": policy_mode, "rules": [r.model_dump() for r in cfg.policy.rules]},
        "seed": seed,
    })
    env = {**os.environ, "MURPHY_RUN_DIR": str(run_dir),
           "FASTMCP_LOG_LEVEL": os.environ.get("FASTMCP_LOG_LEVEL", "WARNING")}
    pkg_root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = os.pathsep.join([pkg_root, *filter(None, [os.environ.get("PYTHONPATH")])])
    return ToolEndpoint(command=sys.executable, args=["-m", PROXY_MODULE, str(run_dir)], env=env, cwd=str(run_dir))


EventHook = Callable[[dict], None]


async def _converse(target: Target, user: User, max_turns: int, rec: Recorder, budget: int,
                    on_event: EventHook | None = None) -> tuple[str, int, int]:
    history: list[dict] = []
    target_tokens = sim_tokens = 0
    seen_tools = 0
    for _ in range(max_turns):
        turn = await user.next(history)
        sim_tokens += turn.tokens
        if turn.message or turn.status != "continue":  # always record the end signal (replay needs it)
            rec.log("user", text=turn.message, status=turn.status)
        if turn.message:
            history.append({"role": "user", "text": turn.message})
        if turn.status != "continue":
            return turn.status, target_tokens, sim_tokens
        reply = await target.send(turn.message)
        target_tokens += reply.tokens
        rec.log("agent", text=reply.text)
        history.append({"role": "agent", "text": reply.text})
        tools = rec.tool_events()
        if on_event:  # live view (murphy chat): tool calls made during this turn, then the reply
            for event in tools[seen_tools:]:
                on_event(event)
            on_event({"kind": "agent", "text": reply.text})
        seen_tools = len(tools)
        if len(tools) > budget:
            return "stuck", target_tokens, sim_tokens
    return "patience_exhausted", target_tokens, sim_tokens


async def run_one(
    cfg: ProjectConfig,
    persona: PersonaConfig,
    scenario: FaultScenario,
    target: Target,
    user: User,
    checks: list[Check],
    run_dir: Path,
    policy_mode: PolicyMode | None = None,
    replay_of: str | None = None,
    seed: int | None = None,
    on_event: EventHook | None = None,
) -> RunResult:
    mode = policy_mode or cfg.policy.mode
    seed = cfg.seed if seed is None else seed
    run_dir = run_dir.resolve()  # subprocesses run with other working directories
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "meta.json", {
        "persona": persona.id, "fault": scenario.id, "scenario": scenario.model_dump(), "policy_mode": mode,
        "seed": seed, "target": target.label, "replay_of": replay_of, "config_hash": config_hash(cfg),
        "config": str(cfg.source) if cfg.source else None,
    })
    rec = Recorder(run_dir)
    budget = run_budget(cfg)
    start = time.time()
    target_tokens = sim_tokens = 0
    try:
        await target.start(tool_endpoint(cfg, run_dir, scenario, mode, seed))
        end_reason, target_tokens, sim_tokens = await asyncio.wait_for(
            _converse(target, user, cfg.max_turns(persona), rec, budget, on_event), cfg.limits.run_timeout_s
        )
    except TimeoutError:
        end_reason = "timeout"
    except Exception as exc:  # a crashing agent is a finding, not a harness failure
        end_reason = f"error: {type(exc).__name__}: {exc}"
    finally:
        try:
            await target.close()
        except Exception:
            pass

    trace = rec.merge()
    ctx = RunContext(run_dir=run_dir, persona=persona, trace=trace, end_reason=end_reason, vars=persona.vars)
    results = run_checks(checks, ctx)
    write_json(run_dir / "checks.json", [r.to_dict() for r in results])
    passed, labels, hint = decide(results, end_reason, bool(persona.vars.get("accept_any_end")))
    tools = ctx.tool_events
    result = RunResult(
        persona=persona.id, fault=scenario.id, target=target.label, policy_mode=mode, seed=seed,
        passed=passed, labels=labels, hint=hint, end_reason=end_reason,
        turns=sum(1 for e in trace if e["kind"] == "user" and e.get("text")), tool_calls=len(tools),
        faults_fired=sum(1 for e in tools if e.get("fault")),
        policy_violations=sum(len(e.get("policy", {}).get("violations", [])) for e in tools),
        policy_blocks=sum(1 for e in tools if e.get("policy", {}).get("blocked")),
        checks=[r.to_dict() for r in results], target_tokens=target_tokens, sim_tokens=sim_tokens,
        wall_s=round(time.time() - start, 1), config_hash=config_hash(cfg), replay_of=replay_of,
    )
    write_json(run_dir / "result.json", result.model_dump())
    return result


def matrix_dir_for(runs_root: Path, cfg: ProjectConfig, target_label: str, mode: str) -> Path:
    slug = "".join(c if c.isalnum() else "-" for c in target_label).strip("-")
    # Random suffix: two runs started in the same second must never share (and interleave) a directory.
    return runs_root / f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}_{cfg.name}_{slug}_{mode}"


def point_latest(matrix_dir: Path) -> None:
    latest = matrix_dir.parent / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(matrix_dir.name)
    except OSError:
        (matrix_dir.parent / "LATEST").write_text(matrix_dir.name)


async def run_matrix(
    cfg: ProjectConfig,
    personas: list[PersonaConfig],
    scenarios: list[FaultScenario],
    make_target: Callable[[], Target],
    make_user: Callable[[PersonaConfig], User],
    checks: list[Check],
    matrix_dir: Path,
    policy_mode: PolicyMode | None = None,
    on_result: Callable[[RunResult], None] | None = None,
    on_event: EventHook | None = None,
) -> list[RunResult]:
    if matrix_dir.exists() and any(matrix_dir.iterdir()):
        raise FileExistsError(f"{matrix_dir} is not empty; refusing to mix runs")
    matrix_dir.mkdir(parents=True, exist_ok=True)
    write_json(matrix_dir / "project.json", {
        "name": cfg.name, "config": str(cfg.source) if cfg.source else None, "config_hash": config_hash(cfg),
        "faults": [s.model_dump() for s in scenarios], "policy": cfg.policy.model_dump(),
        "checks": [c.model_dump() for c in cfg.checks], "ci": cfg.ci.model_dump(),
        "personas": [{"id": p.id, "description": p.description, "goal": p.goal} for p in personas],
    })
    point_latest(matrix_dir)
    results = []
    for persona in personas:
        for scenario in scenarios:
            result = await run_one(cfg, persona, scenario, make_target(), make_user(persona), checks,
                                   matrix_dir / f"{persona.id}__{scenario.id}", policy_mode, on_event=on_event)
            results.append(result)
            if on_result:
                on_result(result)
    return results


def load_result(cell_dir: Path) -> RunResult:
    return RunResult.model_validate(json.loads((cell_dir / "result.json").read_text()))
