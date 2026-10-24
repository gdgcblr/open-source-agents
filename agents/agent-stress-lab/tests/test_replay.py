from helpers import scripted_cfg, scripted_matrix

from murphy.checks import build_checks
from murphy.replay import recorded_turns, render_diff, replay
from murphy.targets import build_target


async def _dup_cell(tmp_path):
    cfg, results = await scripted_matrix(tmp_path)
    assert [r.verdict for r in results] == ["PASS", "FAIL"]
    return cfg, tmp_path / "cooperative__timeout"


async def test_replay_with_fixed_agent_flips_to_pass(tmp_path):
    cfg, cell = await _dup_cell(tmp_path)
    assert [t.message for t in recorded_turns(cell) if t.message] == cfg.user.extras["messages"]
    before, after, out = await replay(cfg, cell, build_target(cfg.target, "scripted_agents:fixed_policy"),
                                      build_checks(cfg.checks))
    assert (before.passed, after.passed) == (False, True)
    assert after.replay_of == "cooperative__timeout" and out.name.startswith("cooperative__timeout__replay-")
    diff = render_diff(before, after, cell, out)
    assert "FAIL [dup]" in diff and "PASS" in diff


async def test_replay_with_enforced_policy_rescues_naive_agent(tmp_path):
    cfg, cell = await _dup_cell(tmp_path)
    _, after, out = await replay(cfg, cell, build_target(cfg.target), build_checks(cfg.checks), policy_mode="enforce")
    assert after.passed and after.policy_blocks >= 1
    assert "⛔" in render_diff(_, after, cell, out)
