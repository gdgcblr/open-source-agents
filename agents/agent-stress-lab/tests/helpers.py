from pathlib import Path

from conftest import SCRIPTED_CONFIG

from murphy.checks import build_checks
from murphy.config.loader import load_config
from murphy.core.orchestrator import run_matrix, run_one
from murphy.targets import build_target
from murphy.users import build_user


def scripted_cfg():
    return load_config(SCRIPTED_CONFIG)


async def run_cell(run_dir: Path, fault: str = "timeout", policy: str = "scripted_agents:naive_policy",
                   mode: str | None = None, messages: list[str] | None = None, final_status: str = "goal_met"):
    cfg = scripted_cfg()
    persona = cfg.personas[0]
    if messages is not None:
        cfg.user.__pydantic_extra__.update(messages=messages, final_status=final_status)
    user = build_user(cfg.user, persona, cfg.seed, cfg.max_turns(persona))
    return await run_one(cfg, persona, cfg.scenario(fault), build_target(cfg.target, policy), user,
                         build_checks(cfg.checks), run_dir, mode)


async def scripted_matrix(matrix_dir: Path, policy: str = "scripted_agents:naive_policy"):
    cfg = scripted_cfg()
    return cfg, await run_matrix(
        cfg, cfg.personas, cfg.faults, lambda: build_target(cfg.target, policy),
        lambda p: build_user(cfg.user, p, cfg.seed, cfg.max_turns(p)), build_checks(cfg.checks), matrix_dir,
    )
