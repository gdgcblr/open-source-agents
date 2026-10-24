"""Every bundled example loads, and runs end to end offline with scripted agents and users."""

import threading
from pathlib import Path

import pytest

from murphy.checks import build_checks
from murphy.config.loader import load_config
from murphy.config.schema import TargetConfig, UserConfig
from murphy.core.orchestrator import run_one
from murphy.targets import build_target
from murphy.users import build_user

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.parametrize("name", ["shop_returns", "payments_refunds", "http_support_bot"])
def test_example_config_loads_and_checks_build(name):
    cfg = load_config(EXAMPLES / name / "murphy.yaml")
    assert cfg.personas and build_checks(cfg.checks)


def scripted(cfg, policy=None, messages=(), url=None):
    if policy:
        cfg.target = TargetConfig(type="scripted", policy=policy)
    if url:
        cfg.target = TargetConfig(type="http", url=url)
    cfg.user = UserConfig(type="scripted", messages=list(messages))
    return cfg


async def run(cfg, persona_id, fault, run_dir, policy_mode=None):
    persona = cfg.persona(persona_id)
    return await run_one(cfg, persona, cfg.scenario(fault), build_target(cfg.target),
                         build_user(cfg.user, persona, cfg.seed, cfg.max_turns(persona)),
                         build_checks(cfg.checks), run_dir, policy_mode)


# --- payments_refunds ------------------------------------------------------

def payments(policy):
    return scripted(load_config(EXAMPLES / "payments_refunds" / "murphy.yaml"), policy,
                    ["Please refund PAY-100, the annual plan."])


async def test_payments_naive_double_refunds_under_timeout(tmp_path):
    r = await run(payments("scripted_agents:refund_naive"), "full-refund", "refund-timeout", tmp_path)
    assert not r.passed and r.labels[0] == "dup"


async def test_payments_fixed_and_enforced_pass(tmp_path):
    assert (await run(payments("scripted_agents:refund_fixed"), "full-refund", "refund-timeout", tmp_path / "a")).passed
    r = await run(payments("scripted_agents:refund_naive"), "full-refund", "refund-timeout", tmp_path / "b", "enforce")
    assert r.passed and r.policy_blocks >= 1


async def test_payments_refund_without_policy_check_is_unsafe_and_wrong(tmp_path):
    r = await run(payments("scripted_agents:refund_without_policy_check"), "outside-window", "no-fault", tmp_path)
    assert set(r.labels) >= {"unsafe", "wrong"}


# --- http_support_bot --------------------------------------------------------

@pytest.fixture
def support_bot(monkeypatch):
    import sys

    sys.path.append(str(EXAMPLES))
    from http_support_bot.server import serve

    server = serve(0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setenv("SUPPORT_BOT_URL", url)
    yield url
    server.shutdown()


REPEATS = ["My app crashes every time I log in.", "It's ravi@example.com", "It still crashes when I log in."]


async def test_http_bot_opens_duplicate_tickets(tmp_path, support_bot):
    cfg = scripted(load_config(EXAMPLES / "http_support_bot" / "murphy.yaml"), messages=REPEATS)
    r = await run(cfg, "repeats-problem", "no-fault", tmp_path)
    assert not r.passed and r.labels == ["dup"] and r.tool_calls == 0
    assert "2 ticket(s)" in r.checks[0]["message"]


async def test_http_bot_fixed_mode_opens_one_ticket(tmp_path, support_bot):
    cfg = scripted(load_config(EXAMPLES / "http_support_bot" / "murphy.yaml"), messages=REPEATS,
                   url=f"{support_bot}/chat?mode=fixed")
    r = await run(cfg, "repeats-problem", "no-fault", tmp_path)
    assert r.passed, r.checks
