"""Tests for reusable policy presets and preset inheritance."""

from pathlib import Path
import pytest
from click.testing import CliRunner

from devguard.config import load_config
from devguard.policy import Decision, evaluate_command
from devguard.presets import get_preset, list_presets, PRESETS
from devguard.cli import main


def test_list_and_get_presets():
    """Verify built-in presets exist and have valid structure."""
    presets = list_presets()
    assert len(presets) >= 3
    names = {p.name for p in presets}
    assert "conservative" in names
    assert "development" in names
    assert "custom" in names

    cons = get_preset("conservative")
    assert cons.default_policy == "deny"
    assert ("git", "status") in cons.allow_rules
    assert ("rm", "-rf") in cons.deny_rules

    dev = get_preset("development")
    assert dev.default_policy == "ask"
    assert ("python3", "-m", "pytest") in dev.allow_rules

    with pytest.raises(ValueError, match="Unknown preset"):
        get_preset("nonexistent_preset_xyz")


def test_preset_inheritance_in_yaml(tmp_path: Path):
    """Config with 'preset: development' inherits development rules and allows overrides."""
    config_file = tmp_path / "devguard.yaml"
    config_file.write_text(
        "preset: development\n"
        "allow:\n"
        "  - ['my-custom-test', 'run']\n"
        "deny:\n"
        "  - ['git', 'push', 'origin', 'main']\n",
        encoding="utf-8",
    )
    loaded = load_config(config_file)
    assert loaded.default_policy == "ask"
    # Inherited allow rule
    assert ("git", "status") in loaded.allow_rules
    # User's added allow rule
    assert ("my-custom-test", "run") in loaded.allow_rules
    # Inherited deny rule
    assert ("git", "reset", "--hard") in loaded.deny_rules
    # User's added deny rule
    assert ("git", "push", "origin", "main") in loaded.deny_rules


def test_preset_deny_cannot_be_overridden_by_user_allow(tmp_path: Path):
    """A user cannot bypass a preset's deny rule by adding it to allow list."""
    config_file = tmp_path / "bypass_attempt.yaml"
    config_file.write_text(
        "preset: development\n"
        "allow:\n"
        "  - ['git', 'reset', '--hard']\n",  # Dangerous attempt to allow
        encoding="utf-8",
    )
    loaded = load_config(config_file)
    # The deny rule from the preset must override the user's attempt to allow it
    res = evaluate_command(["git", "reset", "--hard"], loaded)
    assert res.decision == Decision.DENY
    assert ("git", "reset", "--hard") in loaded.deny_rules
    assert ("git", "reset", "--hard") not in loaded.allow_rules


def test_cli_preset_commands(runner: CliRunner):
    """Test preset list and show CLI commands."""
    res_list = runner.invoke(main, ["preset", "list"])
    assert res_list.exit_code == 0
    assert "CONSERVATIVE" in res_list.output
    assert "DEVELOPMENT" in res_list.output

    res_show = runner.invoke(main, ["preset", "show", "conservative"])
    assert res_show.exit_code == 0
    assert "CONSERVATIVE" in res_show.output
    assert "ALLOW Rules:" in res_show.output
    assert "DENY Rules" in res_show.output


def test_cli_init_with_preset(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test 'devguard init --preset development'."""
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(main, ["init", "--preset", "development"])
    assert res.exit_code == 0
    assert "using preset 'development'" in res.output
    content = Path("devguard.yaml").read_text(encoding="utf-8")
    assert "preset: development" in content

