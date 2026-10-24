"""What to do next on an issue, following the repo's own norms instead of a generic template.

Deterministic on purpose: whether to ask first, wait, or just start depends on evidence
(claims, maintainer policy, "already fixed" comments), not on a model's guess.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .models import SKIP_FLAGS, Candidate
from .signals import days_between


def next_step(candidate: Candidate, conventions: Dict[str, object], first_file: Optional[str], now) -> Dict[str, object]:
    signals = candidate.signals
    flags = set(candidate.flags)
    step: Dict[str, object] = {"action": "", "why": "", "comment_draft": None, "checklist": []}

    if candidate.verdict == "skip":
        step["action"] = "Don't start this one; pick another issue."
        step["why"] = "It is a dead end: " + "; ".join(SKIP_FLAGS[f] for f in sorted(flags & set(SKIP_FLAGS))) + "."
    elif "possibly-resolved" in flags:
        hint = signals.resolved_hints[-1]
        step["action"] = "Confirm it still needs fixing before you write code."
        step["why"] = "@%s says it may already be fixed (%s)." % (hint.author, hint.url)
        step["comment_draft"] = (
            "Hi! Before I start: @%s mentioned this might already be fixed. Could a maintainer confirm "
            "whether this is still needed? If so, I'd like to work on it." % hint.author
        )
    elif "recently-claimed" in flags and not signals.open_policy:
        claim = signals.active_claims[-1]
        age = days_between(claim.created_at, now)
        step["action"] = "Ask whether the earlier claim is still active before starting."
        step["why"] = "@%s asked to work on it %s (%s)." % (claim.author, _ago(age), claim.url)
        step["comment_draft"] = (
            "Hi @%s, are you still working on this? If not, I'd be happy to pick it up." % claim.author
        )
    elif signals is not None and signals.open_policy:
        policy = signals.open_policy
        step["action"] = "Start now; no need to ask for assignment."
        step["why"] = "Maintainer @%s: \"%s\" (%s)." % (policy.author, policy.quote, policy.url)
    else:
        step["action"] = "Leave a short comment so others don't duplicate your work, then start."
        step["why"] = "No claims, open PRs or assignment policy found on the issue."
        where = " in `%s`" % first_file if first_file else ""
        step["comment_draft"] = (
            "Hi! I'd like to work on this. My plan is to make the change%s and add a test that covers it. "
            "I'll open a draft PR soon; let me know if someone is already on it." % where
        )

    checklist: List[str] = []
    rules = {rule["rule"] for rule in conventions.get("rules", [])}
    if "cla" in rules:
        checklist.append("Sign the project's CLA before opening the PR.")
    if "dco" in rules:
        checklist.append("Sign off every commit: git commit -s")
    if "conventional_commits" in rules:
        checklist.append("Use a Conventional Commit message, e.g. `fix: ...`.")
    if "changelog" in rules:
        checklist.append("Add a changelog / news entry.")
    tests = conventions.get("test_commands") or []
    if tests:
        checklist.append("Run the tests before pushing: `%s`" % tests[0])
    checklist.append("Write `Fixes #%d` in the PR description so the issue closes when it merges." % candidate.number)
    step["checklist"] = checklist
    return step


def _ago(days: Optional[float]) -> str:
    if days is None:
        return "recently"
    if days < 1:
        return "today"
    return "%d days ago" % days
