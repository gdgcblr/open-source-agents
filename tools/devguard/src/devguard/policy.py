"""Deterministic command policy engine for DevGuard."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
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
    specificity: int = 0
    candidate_matches_count: int = 0
    effective_executable: str = ""
    resolved_path: str | None = None
    config_source: str = "default"
    candidates_considered: list[tuple[str, str, int]] = field(default_factory=list)


def _rule_matches(command_tokens: tuple[str, ...], rule: tuple[str, ...]) -> bool:
    """Determine if a rule matches the command tokens.

    Matching semantics:
    - Matches on structured argument lists, never raw string matching.
    - Resolves executable paths safely: if command is '/usr/bin/git' and rule is ('git', 'status'),
      the basename 'git' matches rule[0].
    - If the rule explicitly includes path separators (e.g. ('/usr/bin/git', 'status')),
      it requires an exact path match.
    - Deceptive names like 'git-evil' or 'git_backup' do NOT match 'git'.
    """
    if len(command_tokens) < len(rule):
        return False

    cmd_exe = command_tokens[0]
    rule_exe = rule[0]

    # Check executable token match
    exe_matches = False
    if cmd_exe == rule_exe:
        exe_matches = True
    elif "/" in cmd_exe or "\\" in cmd_exe:
        base_cmd_exe = Path(cmd_exe).name
        # Only allow basename match if the rule itself didn't specify a path
        if "/" not in rule_exe and "\\" not in rule_exe and base_cmd_exe == rule_exe:
            exe_matches = True

    if not exe_matches:
        return False

    # Check remaining argument tokens
    return command_tokens[1:len(rule)] == rule[1:]


def evaluate_command(
    command: list[str],
    config: PolicyConfig,
    source_name: str | None = None,
) -> PolicyResult:
    """Evaluate a command against the loaded policy rules.

    Matching rules:
    - Commands are matched against structured argument prefixes, NOT raw strings.
    - Matches with longer argument prefixes take precedence over shorter ones (specificity).
    - If rules have equal prefix lengths, DENY > ASK > ALLOW.
    - If no rule matches, fallback to config.default_policy.

    Args:
        command: List of command arguments (e.g. ["git", "status", "-s"]).
        config: Loaded PolicyConfig.
        source_name: Optional override for config source label.

    Returns:
        PolicyResult describing the decision, matched rule, specificity, and explanation.
    """
    source_label = source_name or config.config_source

    if not command:
        default_decision = Decision(config.default_policy)
        return PolicyResult(
            decision=default_decision,
            matched_rule=None,
            reason=f"Empty command provided; applied default policy '{default_decision.value}'.",
            config_source=source_label,
        )

    raw_exe = command[0]
    effective_exe = Path(raw_exe).name if ("/" in raw_exe or "\\" in raw_exe) else raw_exe
    resolved_path = shutil.which(raw_exe) if not ("/" in raw_exe or "\\" in raw_exe) else str(Path(raw_exe).resolve())

    cmd_tuple = tuple(command)
    matches: list[tuple[int, int, Decision, tuple[str, ...]]] = []

    # Check DENY rules
    for rule in config.deny_rules:
        if _rule_matches(cmd_tuple, rule):
            matches.append((len(rule), _DECISION_PRIORITY[Decision.DENY], Decision.DENY, rule))

    # Check ASK rules
    for rule in config.ask_rules:
        if _rule_matches(cmd_tuple, rule):
            matches.append((len(rule), _DECISION_PRIORITY[Decision.ASK], Decision.ASK, rule))

    # Check ALLOW rules
    for rule in config.allow_rules:
        if _rule_matches(cmd_tuple, rule):
            matches.append((len(rule), _DECISION_PRIORITY[Decision.ALLOW], Decision.ALLOW, rule))

    candidates_list: list[tuple[str, str, int]] = [
        (" ".join(m[3]), m[2].value.upper(), m[0]) for m in matches
    ]

    if matches:
        # Sort by:
        # 1. Prefix length descending (longest prefix wins)
        # 2. Priority descending (DENY > ASK > ALLOW)
        matches.sort(key=lambda m: (m[0], m[1]), reverse=True)
        specificity, _, best_decision, best_rule = matches[0]

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
            specificity=specificity,
            candidate_matches_count=len(matches),
            effective_executable=effective_exe,
            resolved_path=resolved_path,
            config_source=source_label,
            candidates_considered=candidates_list,
        )

    # No matching rule -> fallback to default policy
    default_decision = Decision(config.default_policy)
    return PolicyResult(
        decision=default_decision,
        matched_rule=None,
        reason=f"No matching rule found; applied default policy '{default_decision.value}'.",
        specificity=0,
        candidate_matches_count=0,
        effective_executable=effective_exe,
        resolved_path=resolved_path,
        config_source=source_label,
        candidates_considered=[],
    )
