"""Reusable policy presets for DevGuard."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from devguard.config import PolicyConfig


@dataclass(frozen=True)
class PresetMetadata:
    """Metadata describing a policy preset."""
    name: str
    description: str
    risks_and_tradeoffs: str
    config: PolicyConfig


PRESETS: dict[str, PresetMetadata] = {
    "conservative": PresetMetadata(
        name="conservative",
        description="High-security policy. Fail-closed default-deny, read-only Git allowed, test and build commands require approval.",
        risks_and_tradeoffs=(
            "Trade-off: Maximizes safety and prevents accidental command execution, but requires frequent interactive approvals "
            "for common developer tasks like running tests or compiling."
        ),
        config=PolicyConfig(
            default_policy="deny",
            allow_rules=[
                ("git", "status"),
                ("git", "diff"),
                ("git", "log"),
                ("git", "branch"),
                ("git", "show"),
            ],
            ask_rules=[
                ("git", "commit"),
                ("git", "push"),
                ("python3", "-m", "pytest"),
                ("pytest",),
                ("npm", "test"),
                ("cargo", "test"),
            ],
            deny_rules=[
                ("rm", "-rf"),
                ("git", "reset", "--hard"),
                ("git", "clean", "-fdx"),
                ("git", "push", "--force"),
                ("chmod", "-R", "777"),
            ],
            preset="conservative",
            config_source="preset:conservative",
        ),
    ),
    "development": PresetMetadata(
        name="development",
        description="Balanced developer workflow. Read-only Git and recognized test commands run automatically. Dangerous mutations denied.",
        risks_and_tradeoffs=(
            "Trade-off: Fast day-to-day feedback loops without prompts for read-only Git queries and standard test runners, "
            "while strictly denying destructive filesystem and history operations."
        ),
        config=PolicyConfig(
            default_policy="ask",
            allow_rules=[
                ("git", "status"),
                ("git", "diff"),
                ("git", "log"),
                ("git", "branch"),
                ("git", "show"),
                ("python3", "-m", "pytest"),
                ("pytest",),
                ("npm", "test"),
                ("cargo", "test"),
                ("echo",),
            ],
            ask_rules=[
                ("git", "commit"),
                ("git", "push"),
                ("npm", "install"),
                ("pip", "install"),
            ],
            deny_rules=[
                ("rm", "-rf"),
                ("git", "reset", "--hard"),
                ("git", "clean", "-fdx"),
                ("git", "push", "--force"),
                ("git", "push", "-f"),
                ("chmod", "-R", "777"),
            ],
            preset="development",
            config_source="preset:development",
        ),
    ),
    "custom": PresetMetadata(
        name="custom",
        description="User-defined policy with no built-in allow rules; default-deny fail-closed baseline.",
        risks_and_tradeoffs="Trade-off: Requires you to explicitly configure every allowed command in devguard.yaml.",
        config=PolicyConfig(
            default_policy="deny",
            allow_rules=[],
            ask_rules=[],
            deny_rules=[
                ("rm", "-rf"),
                ("git", "reset", "--hard"),
                ("git", "clean", "-fdx"),
            ],
            preset="custom",
            config_source="preset:custom",
        ),
    ),
}


def get_preset(name: str) -> PolicyConfig:
    """Retrieve a PolicyConfig instance for a named preset."""
    normalized = name.lower().strip()
    if normalized not in PRESETS:
        available = ", ".join(sorted(PRESETS.keys()))
        raise ValueError(f"Unknown preset '{name}'. Available presets: {available}")
    return PRESETS[normalized].config


def list_presets() -> list[PresetMetadata]:
    """Return all available preset definitions."""
    return list(PRESETS.values())

