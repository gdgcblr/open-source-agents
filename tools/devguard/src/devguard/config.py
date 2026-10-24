"""Configuration loader and schema validator for DevGuard."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml


VALID_POLICIES = {"allow", "ask", "deny"}


class ConfigError(Exception):
    """Raised when DevGuard configuration is missing, unreadable, or invalid."""
    pass


@dataclass(frozen=True)
class PolicyConfig:
    """Parsed and validated policy configuration."""
    default_policy: str = "deny"
    allow_rules: list[tuple[str, ...]] = field(default_factory=list)
    ask_rules: list[tuple[str, ...]] = field(default_factory=list)
    deny_rules: list[tuple[str, ...]] = field(default_factory=list)


def _validate_rule_list(raw_list: Any, section_name: str) -> list[tuple[str, ...]]:
    """Validate that a rule section is a list of string lists."""
    if raw_list is None:
        return []
    if not isinstance(raw_list, list):
        raise ConfigError(f"Section '{section_name}' must be a list of command argument lists.")

    validated: list[tuple[str, ...]] = []
    for idx, rule in enumerate(raw_list):
        if not isinstance(rule, list) or len(rule) == 0:
            raise ConfigError(
                f"Rule #{idx + 1} in '{section_name}' must be a non-empty list of string arguments."
            )
        for token in rule:
            if not isinstance(token, str) or not token.strip():
                raise ConfigError(
                    f"All tokens in rule #{idx + 1} of '{section_name}' must be non-empty strings."
                )
        validated.append(tuple(rule))
    return validated


def load_config(path: str | Path) -> PolicyConfig:
    """Load and validate a YAML policy configuration file.

    Args:
        path: Filepath to the YAML configuration file.

    Returns:
        A validated PolicyConfig object.

    Raises:
        ConfigError: If the file does not exist, is malformed, or violates schema.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {config_path.resolve()}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Malformed YAML in configuration file '{config_path}': {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read configuration file '{config_path}': {exc}") from exc

    if data is None:
        # Empty file, return default fail-closed config
        return PolicyConfig(default_policy="deny")

    if not isinstance(data, dict):
        raise ConfigError("Configuration root must be a YAML mapping/dictionary.")

    # Validate default_policy
    raw_default = data.get("default_policy", "deny")
    if not isinstance(raw_default, str) or raw_default.lower() not in VALID_POLICIES:
        raise ConfigError(
            f"Invalid 'default_policy': '{raw_default}'. Must be one of: {', '.join(sorted(VALID_POLICIES))}."
        )
    default_policy = raw_default.lower()

    allow_rules = _validate_rule_list(data.get("allow"), "allow")
    ask_rules = _validate_rule_list(data.get("ask"), "ask")
    deny_rules = _validate_rule_list(data.get("deny"), "deny")

    return PolicyConfig(
        default_policy=default_policy,
        allow_rules=allow_rules,
        ask_rules=ask_rules,
        deny_rules=deny_rules,
    )

