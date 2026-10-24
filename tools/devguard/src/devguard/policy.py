"""Deterministic command policy engine for DevGuard."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from devguard.config import PolicyConfig


class Decision(str, Enum):
    """Allowed policy outcomes."""
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


# Precedence order among equal-length matches (higher index wins)
# DENY (2) > ASK (1) > ALLOW (0)
_DECISION_PRIORITY = {
    Decision.ALLOW: 0,
    Decision.ASK: 1,
    Decision.DENY: 2,
}


@dataclass(frozen=True)
class PolicyResult:
    """The outcome of evaluating a command against the policy."""
    decision: Decision
    matched_rule: tuple[str, ...] | None
    reason: str


def evaluate_command(command: list[str], config: PolicyConfig) -> PolicyResult:
    """Evaluate a command against the loaded policy rules.

    Matching rules:
    - Commands are matched against structured argument prefixes, NOT raw strings.
    - Matches with longer argument prefixes take precedence over shorter ones.
    - If rules have equal prefix lengths, DENY > ASK > ALLOW.
    - If no rule matches, fallback to config.default_policy.

    Args:
        command: List of command arguments (e.g. ["git", "status", "-s"]).
        config: Loaded PolicyConfig.

    Returns:
        PolicyResult describing the decision, matched rule, and explanation.
    """
    if not command:
        default_decision = Decision(config.default_policy)
        return PolicyResult(
            decision=default_decision,
            matched_rule=None,
            reason=f"Empty command provided; applied default policy '{default_decision.value}'."
        )

    cmd_tuple = tuple(command)
    matches: list[tuple[int, int, Decision, tuple[str, ...]]] = []

    # Check DENY rules
    for rule in config.deny_rules:
        if len(cmd_tuple) >= len(rule) and cmd_tuple[:len(rule)] == rule:
            matches.append((len(rule), _DECISION_PRIORITY[Decision.DENY], Decision.DENY, rule))

    # Check ASK rules
    for rule in config.ask_rules:
        if len(cmd_tuple) >= len(rule) and cmd_tuple[:len(rule)] == rule:
            matches.append((len(rule), _DECISION_PRIORITY[Decision.ASK], Decision.ASK, rule))

    # Check ALLOW rules
    for rule in config.allow_rules:
        if len(cmd_tuple) >= len(rule) and cmd_tuple[:len(rule)] == rule:
            matches.append((len(rule), _DECISION_PRIORITY[Decision.ALLOW], Decision.ALLOW, rule))

    if matches:
        # Sort by:
        # 1. Prefix length descending (longest prefix wins)
        # 2. Priority descending (DENY > ASK > ALLOW)
        matches.sort(key=lambda m: (m[0], m[1]), reverse=True)
        _, _, best_decision, best_rule = matches[0]

        rule_repr = " ".join(best_rule)
        if best_decision == Decision.DENY:
            reason = f"Explicitly denied by rule: [{rule_repr}]"
        elif best_decision == Decision.ASK:
            reason = f"Explicit user confirmation required by rule: [{rule_repr}]"
        else:
            reason = f"Allowed by rule: [{rule_repr}]"

        return PolicyResult(
            decision=best_decision,
            matched_rule=best_rule,
            reason=reason,
        )

    # No matching rule -> fallback to default policy
    default_decision = Decision(config.default_policy)
    return PolicyResult(
        decision=default_decision,
        matched_rule=None,
        reason=f"No matching rule found; applied default policy '{default_decision.value}'."
    )

