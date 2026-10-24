"""Unit tests for DevGuard configuration loader and schema validator."""

import pytest
from pathlib import Path
from devguard.config import ConfigError, PolicyConfig, load_config


def test_load_valid_config(sample_config_file: Path):
    """Test loading a standard valid configuration file."""
    config = load_config(sample_config_file)
    assert isinstance(config, PolicyConfig)
    assert config.default_policy == "ask"
    assert ("git", "status") in config.allow_rules
    assert ("git", "commit") in config.ask_rules
    assert ("git", "reset", "--hard") in config.deny_rules


def test_load_empty_file(tmp_path: Path):
    """An empty configuration file should default to fail-closed policy (deny)."""
    empty_file = tmp_path / "empty.yaml"
    empty_file.write_text("", encoding="utf-8")
    config = load_config(empty_file)
    assert config.default_policy == "deny"
    assert config.allow_rules == []
    assert config.ask_rules == []
    assert config.deny_rules == []


def test_missing_config_file(tmp_path: Path):
    """Attempting to load a nonexistent file should raise ConfigError."""
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(ConfigError, match="Configuration file not found"):
        load_config(missing)


def test_malformed_yaml(tmp_path: Path):
    """Syntactically invalid YAML should raise ConfigError."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("default_policy: [unclosed list", encoding="utf-8")
    with pytest.raises(ConfigError, match="Malformed YAML"):
        load_config(bad_yaml)


def test_non_dict_root(tmp_path: Path):
    """A YAML file that is a scalar or list at root must raise ConfigError."""
    non_dict = tmp_path / "list_root.yaml"
    non_dict.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="YAML mapping/dictionary"):
        load_config(non_dict)


def test_invalid_default_policy(tmp_path: Path):
    """An invalid default_policy value must raise ConfigError."""
    bad_policy = tmp_path / "bad_policy.yaml"
    bad_policy.write_text("default_policy: execute_always\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid 'default_policy'"):
        load_config(bad_policy)


def test_invalid_rule_structure(tmp_path: Path):
    """Rules that are not lists of strings must raise ConfigError."""
    bad_rules = tmp_path / "bad_rules.yaml"
    bad_rules.write_text("allow: 'git status'\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a list of command argument lists"):
        load_config(bad_rules)


def test_empty_sublist_rule(tmp_path: Path):
    """Rules that contain empty lists must raise ConfigError."""
    bad_rule = tmp_path / "empty_rule.yaml"
    bad_rule.write_text("allow:\n  - []\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a non-empty list of string arguments"):
        load_config(bad_rule)


def test_non_string_token(tmp_path: Path):
    """Rules containing numbers or non-string tokens must raise ConfigError."""
    bad_token = tmp_path / "bad_token.yaml"
    bad_token.write_text("allow:\n  - ['git', 123]\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must be non-empty strings"):
        load_config(bad_token)

