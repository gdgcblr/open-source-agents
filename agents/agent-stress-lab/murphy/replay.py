"""Replay a recorded run: same persona, same faults, same seed, same user turns (verbatim,
with their recorded status) against a possibly different target or policy mode.
The target model still runs live; divergence is flagged."""

from __future__ import annotations

import json
from pathlib import Path

from murphy.checks import Check
from murphy.config.schema import FaultScenario, PolicyMode, ProjectConfig
from murphy.core.orchestrator import RunResult, load_result, run_one
from murphy.core.trace import read_jsonl, write_json
from murphy.targets.base import Target
from murphy.users.base import User, UserTurn
from murphy.users.replay import ReplayUser


def recorded_turns(cell_dir: Path) -> list[UserTurn]:
    return [UserTurn(e["text"], e.get("status", "continue"))
            for e in read_jsonl(cell_dir / "conversation.jsonl") if e["kind"] == "user"]


def replay_dir_for(cell_dir: Path, label: str) -> Path:
    slug = "".join(c if c.isalnum() else "-" for c in label).strip("-")
    n = 1
    while (cell_dir.parent / f"{cell_dir.name}__replay-{slug}-{n}").exists():
        n += 1
    return cell_dir.parent / f"{cell_dir.name}__replay-{slug}-{n}"


async def replay(
    cfg: ProjectConfig,
    cell_dir: Path,
    target: Target,
    checks: list[Check],
    fallback: User | None = None,
    policy_mode: PolicyMode | None = None,
) -> tuple[RunResult, RunResult, Path]:
    meta = json.loads((cell_dir / "meta.json").read_text())
    before = load_result(cell_dir)
    user = ReplayUser(recorded_turns(cell_dir), fallback)
    out = replay_dir_for(cell_dir, target.label)
    after = await run_one(
        cfg, cfg.persona(meta["persona"]), FaultScenario.model_validate(meta["scenario"]), target, user, checks, out,
        policy_mode=policy_mode or meta["policy_mode"], replay_of=cell_dir.name, seed=meta["seed"],
    )
    if user.diverged:
        after.replay_diverged = True
        write_json(out / "result.json", after.model_dump())
    return before, after, out


def _tools(cell_dir: Path) -> str:
    marks = []
    for e in read_jsonl(cell_dir / "tools.jsonl"):
        mark = "⛔" if e.get("policy", {}).get("blocked") else "⚡" if e.get("fault") in ("timeout_after_commit", "error_500") else ""
        marks.append(e["tool"] + mark)
    return " → ".join(marks) or "(no tool calls)"


def render_diff(before: RunResult, after: RunResult, before_dir: Path, after_dir: Path) -> str:
    def verdict(r: RunResult) -> str:
        return r.verdict + (f" [{', '.join(r.labels)}]" if r.labels else "")

    lines = [
        f"replay {before.persona} × {before.fault} · same user turns · same faults · seed {before.seed}",
        "",
        f" before  [{before.target}, policy={before.policy_mode}]  {verdict(before)}",
        f"         tools: {_tools(before_dir)}",
        f" after   [{after.target}, policy={after.policy_mode}]  {verdict(after)}",
        f"         tools: {_tools(after_dir)}",
    ]
    if after.replay_diverged:
        lines.append(" note    recorded user turns ran out; live simulator continued (replay_diverged)")
    return "\n".join(lines) + "\n"
