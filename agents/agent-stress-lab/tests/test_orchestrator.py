from helpers import run_cell

from murphy.core.trace import read_jsonl


async def test_naive_agent_passes_without_faults(run_dir):
    r = await run_cell(run_dir, fault="no-fault")
    assert r.passed and r.end_reason == "goal_met" and r.labels == []


async def test_naive_agent_duplicates_under_committed_timeout(run_dir):
    r = await run_cell(run_dir)
    assert not r.passed and r.primary_label == "dup"
    assert r.faults_fired == 1 and r.policy_violations >= 1
    assert {c["id"]: c["passed"] for c in r.checks} == {"single-booking": False, "outcome": True}


async def test_fixed_agent_survives_committed_timeout(run_dir):
    r = await run_cell(run_dir, policy="scripted_agents:fixed_policy")
    assert r.passed


async def test_enforced_policy_rescues_naive_agent(run_dir):
    r = await run_cell(run_dir, mode="enforce")
    assert r.passed and r.policy_blocks >= 1 and r.policy_mode == "enforce"


async def test_claimed_success_without_booking_is_wrong(run_dir):
    r = await run_cell(run_dir, fault="no-fault", policy="scripted_agents:claims_success_policy")
    assert r.labels == ["wrong"]


async def test_user_giving_up_adds_quit(run_dir):
    r = await run_cell(run_dir, fault="no-fault", policy="scripted_agents:claims_success_policy",
                       messages=["hi"], final_status="give_up")
    assert r.labels == ["wrong", "quit"]


async def test_artifacts_and_trace_order(run_dir):
    await run_cell(run_dir)
    for name in ("meta.json", "proxy.json", "result.json", "checks.json", "state.json", "tools.jsonl",
                 "conversation.jsonl", "trace.jsonl"):
        assert (run_dir / name).exists(), name
    trace = read_jsonl(run_dir / "trace.jsonl")
    kinds = [e["kind"] for e in trace]
    assert kinds[0] == "user" and kinds.index("tool") < kinds.index("agent")
    assert all(e["v"] == 1 for e in trace)
