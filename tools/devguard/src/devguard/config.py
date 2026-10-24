"""Configuration loader and schema validator for DevGuard."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml


VALID_POLICIES = {"allow", "ask", "deny"}

# Executables that must have explicit subarguments in allow rules to prevent arbitrary execution
UNSAFE_BROAD_EXECUTABLES = {
    "git",
    "python",
    "python3",
    "npm",
    "npx",
    "yarn",
    "pnpm",
    "uv",
    "pip",
    "pip3",
    "bash",
    "sh",
    "zsh",
    "sudo",
    "curl",
    "wget",
}


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
    preset: str | None = None
    config_source: str = "default"


def _validate_rule_list(
    raw_list: Any,
    section_name: str,
    strict_broad_check: bool = True,
) -> list[tuple[str, ...]]:
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

        # Enforce that multi-command tools cannot be broadly allowed with zero subarguments
        if section_name == "allow" and strict_broad_check and len(rule) == 1:
            base_exe = Path(rule[0]).name.lower()
            if base_exe in UNSAFE_BROAD_EXECUTABLES:
                raise ConfigError(
                    f"Broad allow rule '[{rule[0]}]' is unsafe. Executable '{rule[0]}' requires explicit "
                    f"subarguments (for example, ['{rule[0]}', 'status']). "
                    f"Do not treat an executable prefix as permission to run arbitrary arguments."
                )

        validated.append(tuple(rule))
    return validated


def parse_config_dict(data: dict[str, Any], source_label: str = "custom") -> PolicyConfig:
    """Validate a parsed dictionary into a PolicyConfig object."""
    if not isinstance(data, dict):
        raise ConfigError("Configuration root must be a YAML mapping/dictionary.")

    preset_name = data.get("preset")
    base_preset_cfg = None
    if preset_name is not None:
        if not isinstance(preset_name, str):
            raise ConfigError("Field 'preset' must be a string name if specified.")
        from devguard.presets import get_preset
        try:
            base_preset_cfg = get_preset(preset_name)
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc

    raw_default = data.get("default_policy")
    if raw_default is not None:
        if not isinstance(raw_default, str) or raw_default.lower() not in VALID_POLICIES:
            raise ConfigError(
                f"Invalid 'default_policy': '{raw_default}'. Must be one of: {', '.join(sorted(VALID_POLICIES))}."
            )
        default_policy = raw_default.lower()
    else:
        default_policy = base_preset_cfg.default_policy if base_preset_cfg else "deny"

    allow_rules = _validate_rule_list(data.get("allow"), "allow")
    ask_rules = _validate_rule_list(data.get("ask"), "ask")
    deny_rules = _validate_rule_list(data.get("deny"), "deny")

    parsed_overlay = PolicyConfig(
        default_policy=default_policy,
        allow_rules=allow_rules,
        ask_rules=ask_rules,
        deny_rules=deny_rules,
        preset=preset_name,
        config_source=source_label,
    )

    if base_preset_cfg:
        return merge_configs(
            base_preset_cfg,
            parsed_overlay,
            merged_source=f"{source_label} (preset: {preset_name})",
        )

    return parsed_overlay


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
        return PolicyConfig(default_policy="deny", config_source=str(config_path))

    return parse_config_dict(data, source_label=str(config_path))


def get_user_config_path() -> Path | None:
    """Return the path to the user-level config if it exists."""
    home = Path.home()
    candidates = [
        home / ".config" / "devguard" / "config.yaml",
        home / ".config" / "devguard" / "devguard.yaml",
        home / ".devguard.yaml",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def merge_configs(base: PolicyConfig, overlay: PolicyConfig, merged_source: str = "merged") -> PolicyConfig:
    """Merge base config with overlay config.

    Precedence rules:
    - Explicit deny rules from both base and overlay are combined (authoritative deny).
    - An allow rule in either config CANNOT override an explicit deny rule.
    - Overlay default_policy overrides base if specified.
    """
    # Combine deny rules (deduplicated)
    all_deny = list(dict.fromkeys(base.deny_rules + overlay.deny_rules))

    # Combine ask rules (excluding any covered by deny rules)
    all_ask = [r for r in dict.fromkeys(base.ask_rules + overlay.ask_rules) if r not in all_deny]

    # Combine allow rules (excluding any covered by deny or ask rules)
    all_allow = [
        r for r in dict.fromkeys(base.allow_rules + overlay.allow_rules)
        if r not in all_deny and r not in all_ask
    ]

    default_policy = overlay.default_policy or base.default_policy

    return PolicyConfig(
        default_policy=default_policy,
        allow_rules=all_allow,
        ask_rules=all_ask,
        deny_rules=all_deny,
        preset=overlay.preset or base.preset,
        config_source=merged_source,
    )


def load_resolved_config(
    project_path: str | Path | None = None,
    user_path: str | Path | None = None,
) -> PolicyConfig:
    """Load and merge user-level and project-level configs."""
    # 1. Load user config if present
    u_path = Path(user_path) if user_path else get_user_config_path()
    user_cfg = load_config(u_path) if (u_path and u_path.exists()) else None

    # 2. Load project config if present
    p_path = Path(project_path) if project_path else Path("devguard.yaml")
    project_cfg = load_config(p_path) if p_path.exists() else None

    if project_cfg and user_cfg:
        return merge_configs(user_cfg, project_cfg, merged_source=f"{p_path} (merged with {u_path})")
    elif project_cfg:
        return project_cfg
    elif user_cfg:
        return user_cfg
    else:
        # Fall-closed default
        return PolicyConfig(default_policy="deny", config_source="default-deny")
