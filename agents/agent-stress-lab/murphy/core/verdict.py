"""Turn check results + how the conversation ended into a verdict and labels."""

from __future__ import annotations

from murphy.checks.base import CheckResult

QUIT_REASONS = {"give_up", "patience_exhausted"}
BUILTIN_HINTS = {
    "quit": "The user gave up before the task was done. Ask for missing info earlier, keep replies short, recover from tool errors without stalling.",
    "stuck": "The run hit a hard limit (timeout or tool-call budget). Look for loops on failing tools.",
    "error": "The agent, simulator or a tool crashed. See end_reason for the exception.",
}


def decide(results: list[CheckResult], end_reason: str, accept_any_end: bool = False) -> tuple[bool, list[str], str]:
    """Returns (passed, labels, hint). Labels keep config order; built-in quit/stuck added from end reason."""
    failed = [r for r in results if not r.passed]
    labels = list(dict.fromkeys(r.label for r in failed))
    hint = next((r.hint for r in failed if r.hint), "")
    if end_reason != "goal_met" and not accept_any_end:
        label = "quit" if end_reason in QUIT_REASONS else "error" if end_reason.startswith("error") else "stuck"
        labels.append(label)
        hint = hint or BUILTIN_HINTS[label]
    return not labels, labels, hint
