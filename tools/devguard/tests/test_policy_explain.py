"""Tests for stronger command policy matching and policy explain command."""

import pytest
from pathlib import Path
from click.testing import CliRunner

from devguard.config import ConfigError, PolicyConfig, merge_configs, load_config
from devguard.policy import Decision, evaluate_command
from devguard.cli import main


@pytest.fixture
def complex_policy():
    return PolicyConfig(
        default_policy="deny",
        allow_rules=[
            ("git", "status"),
            ("git", "diff"),
            ("python3", "-m", "pytest"),
            ("/usr/local/bin/safe-tool", "run"),
        ],
        ask_rules=[
            ("git", "reset"),
            ("git", "commit"),
        ],
        deny_rules=[
            ("git", "reset", "--hard"),
            ("rm", "-rf"),
            ("git", "clean", "-fdx"),
        ],
        config_source="test_policy.yaml",
    )


def test_path_normalization_matches_basename(complex_policy: PolicyConfig):
    """Running /usr/bin/git status matches ('git', 'status') rule."""
    res = evaluate_command(["/usr/bin/git", "status"], complex_policy)
    assert res.decision == Decision.ALLOW
    assert res.matched_rule == ("git", "status")
    assert res.effective_executable == "git"


def test_exact_path_rule_matching(complex_policy: PolicyConfig):
    """Rule specifying /usr/local/bin/safe-tool matches only that exact path."""
    res = evaluate_command(["/usr/local/bin/safe-tool", "run"], complex_policy)
    assert res.decision == Decision.ALLOW
    assert res.matched_rule == ("/usr/local/bin/safe-tool", "run")

    # A different path with same basename should not match the exact-path rule
    res_other = evaluate_command(["/tmp/safe-tool", "run"], complex_policy)
    assert res_other.decision == Decision.DENY


def test_deceptive_executable_names_refused(complex_policy: PolicyConfig):
    """Executables with deceptive prefixes like 'git-bad' must not match 'git' rules."""
    res = evaluate_command(["git-bad", "status"], complex_policy)
    assert res.decision == Decision.DENY
    assert res.matched_rule is None

    res2 = evaluate_command(["/usr/bin/git_evil", "status"], complex_policy)
    assert res2.decision == Decision.DENY
    assert res2.matched_rule is None


def test_unsafe_broad_allow_rule_rejected(tmp_path: Path):
    """Adding an allow rule like ['git'] without subarguments must be rejected by schema."""
    bad_cfg = tmp_path / "broad.yaml"
    bad_cfg.write_text("allow:\n  - ['git']\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Broad allow rule"):
        load_config(bad_cfg)


def test_merge_configs_authoritative_deny():
    """Merging user and project config ensures explicit deny rules are always authoritative."""
    user_cfg = PolicyConfig(
        default_policy="ask",
        allow_rules=[("git", "reset", "--hard")],  # User tries to allow
        deny_rules=[("rm", "-rf")],
    )
    proj_cfg = PolicyConfig(
        default_policy="deny",
        deny_rules=[("git", "reset", "--hard")],  # Project explicitly denies
    )
    merged = merge_configs(user_cfg, proj_cfg)
    assert ("git", "reset", "--hard") in merged.deny_rules
    assert ("git", "reset", "--hard") not in merged.allow_rules


def test_policy_explain_cli_allowed(tmp_path: Path, sample_config_file: Path):
    """Test 'devguard policy explain -- git status' outputs full explanation."""
    runner = CliRunner()
    res = runner.invoke(
        main,
        ["policy", "explain", "-c", str(sample_config_file), "--", "git", "status"],
    )
    assert res.exit_code == 0
    assert "Policy Explanation" in res.output
    assert "ALLOW" in res.output
    assert "[git status]" in res.output
    assert "2 argument token(s)" in res.output


def test_policy_explain_cli_denied(tmp_path: Path, sample_config_file: Path):
    """Test 'devguard policy explain -- git reset --hard' shows explicit deny."""
    runner = CliRunner()
    res = runner.invoke(
        main,
        ["policy", "explain", "-c", str(sample_config_file), "--", "git", "reset", "--hard"],
    )
    assert res.exit_code == 0
    assert "DENY" in res.output
    assert "[git reset --hard]" in res.output


def test_policy_explain_cli_default_deny(tmp_path: Path, sample_config_file: Path):
    """Test 'devguard policy explain -- unrecognized-tool' shows default policy."""
    runner = CliRunner()
    res = runner.invoke(
        main,
        ["policy", "explain", "-c", str(sample_config_file), "--", "unrecognized-tool"],
    )
    assert res.exit_code == 0
    assert "No matching rule found" in res.output
