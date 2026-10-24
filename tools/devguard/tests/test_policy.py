"""Unit tests for DevGuard policy engine and precedence logic."""

import pytest
from devguard.config import PolicyConfig
from devguard.policy import Decision, PolicyResult, evaluate_command


@pytest.fixture
def policy_config():
    return PolicyConfig(
        default_policy="deny",
        allow_rules=[
            ("git", "status"),
            ("git", "diff"),
            ("git", "log"),
            ("python3", "-m", "pytest"),
            ("echo",),
        ],
        ask_rules=[
            ("git", "commit"),
            ("git", "push"),
            ("git", "reset"),  # General git reset asks
        ],
        deny_rules=[
            ("git", "reset", "--hard"),  # Specific git reset --hard is denied
            ("rm", "-rf"),
            ("git", "clean", "-fdx"),
        ],
    )


def test_allow_exact_and_subarguments(policy_config: PolicyConfig):
    """Commands matching an allow rule should be ALLOW, even with extra args."""
    res1 = evaluate_command(["git", "status"], policy_config)
    assert res1.decision == Decision.ALLOW
    assert res1.matched_rule == ("git", "status")

    res2 = evaluate_command(["git", "status", "--short"], policy_config)
    assert res2.decision == Decision.ALLOW
    assert res2.matched_rule == ("git", "status")


def test_ask_command(policy_config: PolicyConfig):
    """Commands matching ask rules should require confirmation."""
    res = evaluate_command(["git", "commit", "-m", "fix: bug"], policy_config)
    assert res.decision == Decision.ASK
    assert res.matched_rule == ("git", "commit")


def test_deny_exact_and_subarguments(policy_config: PolicyConfig):
    """Commands matching deny rules should be DENIED."""
    res = evaluate_command(["git", "clean", "-fdx"], policy_config)
    assert res.decision == Decision.DENY
    assert res.matched_rule == ("git", "clean", "-fdx")


def test_longest_prefix_precedence(policy_config: PolicyConfig):
    """Longer prefix (git reset --hard, len 3) must beat shorter prefix (git reset, len 2)."""
    res = evaluate_command(["git", "reset", "--hard", "HEAD~1"], policy_config)
    assert res.decision == Decision.DENY
    assert res.matched_rule == ("git", "reset", "--hard")

    # Regular git reset should fall back to ask (len 2)
    res_ask = evaluate_command(["git", "reset", "HEAD~1"], policy_config)
    assert res_ask.decision == Decision.ASK
    assert res_ask.matched_rule == ("git", "reset")


def test_deny_beats_allow_at_equal_length():
    """At identical prefix length, DENY must take precedence over ALLOW and ASK."""
    conf = PolicyConfig(
        default_policy="deny",
        allow_rules=[("danger", "cmd")],
        ask_rules=[("danger", "cmd")],
        deny_rules=[("danger", "cmd")],
    )
    res = evaluate_command(["danger", "cmd"], conf)
    assert res.decision == Decision.DENY
    assert res.matched_rule == ("danger", "cmd")


def test_default_deny_when_unmatched():
    """When no rule matches, the default policy (deny) must apply."""
    conf = PolicyConfig(default_policy="deny", allow_rules=[("git", "status")])
    res = evaluate_command(["unrecognized", "binary"], conf)
    assert res.decision == Decision.DENY
    assert res.matched_rule is None
    assert "default policy 'deny'" in res.reason


def test_default_ask_when_unmatched():
    """When default_policy is 'ask' and no rule matches, decision should be ASK."""
    conf = PolicyConfig(default_policy="ask", allow_rules=[("git", "status")])
    res = evaluate_command(["my-tool", "run"], conf)
    assert res.decision == Decision.ASK
    assert res.matched_rule is None


def test_no_raw_string_prefix_matching():
    """Rule for 'git' should not match 'git-crypt' or 'github-cli'."""
    conf = PolicyConfig(
        default_policy="deny",
        allow_rules=[("git",)],
    )
    res = evaluate_command(["git_custom", "status"], conf)
    assert res.decision == Decision.DENY
    assert res.matched_rule is None


def test_empty_command_returns_default(policy_config: PolicyConfig):
    """Empty command list returns default policy with an informative reason."""
    res = evaluate_command([], policy_config)
    assert res.decision == Decision.DENY
    assert res.matched_rule is None
    assert "Empty command" in res.reason

