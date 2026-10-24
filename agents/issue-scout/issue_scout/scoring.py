"""Turn signals into a verdict, a 0-100 score and human-readable reasons.

The weights are deliberately simple so every point can be explained.
"""

from __future__ import annotations

from datetime import datetime

from .models import SKIP_FLAGS, Candidate, Profile
from .signals import days_between

SMALL_LABELS = {"documentation", "docs", "typo", "good first issue", "easy", "beginner", "starter", "trivial"}
LARGE_LABELS = {"feature", "enhancement", "refactor", "epic", "performance", "breaking change", "design"}
# Labels saying the issue still needs a decision before anyone should write code.
UNDECIDED_LABELS = {
    "rfc", "proposal", "discussion", "question", "needs design", "needs-design", "needs decision",
    "needs triage", "needs-triage", "needs discussion", "blocked", "on hold", "waiting for feedback",
}
URGENT_LABELS = {"high priority", "priority: high", "p0", "p1", "critical", "urgent"}
EFFORT_LEVELS = ["small", "medium", "large"]
EFFORT_HOURS = {"small": 1.5, "medium": 4.0, "large": 12.0}
MIN_OUTSIDE_SAMPLE = 3


def estimate_effort(candidate: Candidate) -> str:
    """A rough size guess from labels and how much the issue says. Not a promise."""
    labels = {label.lower() for label in candidate.labels}
    body = candidate.body or ""
    level = 1
    if labels & LARGE_LABELS:
        level += 1
    elif labels & SMALL_LABELS:
        level -= 1
    if len(body) > 2500 or body.count("- [ ]") >= 4:
        level += 1
    return EFFORT_LEVELS[max(0, min(level, 2))]


def evaluate(candidate: Candidate, profile: Profile, now: datetime) -> Candidate:
    signals = candidate.signals
    health = candidate.repo_health
    reasons, flags = [], []
    score = 40

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        reasons.append(("+%d " % points if points >= 0 else "%d " % points) + reason)

    # --- Dead ends ---------------------------------------------------------
    if health is not None and health.archived:
        flags.append("repo-archived")
    if candidate.locked:
        flags.append("locked")
    if signals is not None:
        if signals.assignees:
            flags.append("assigned")
        if signals.pulls_with_state("open"):
            flags.append("open-pr")
        if signals.pulls_with_state("merged"):
            flags.append("merged-pr")
        maintainer_hints = [m for m in signals.resolved_hints if m.is_maintainer]
        if maintainer_hints:
            flags.append("likely-resolved")
        elif signals.resolved_hints:
            flags.append("possibly-resolved")
            add(-20, "a commenter says it may already be fixed")

    # --- Freshness ---------------------------------------------------------
    updated_days = days_between(candidate.updated_at, now)
    created_days = days_between(candidate.created_at, now)
    if updated_days is not None:
        if updated_days <= 14:
            add(15, "active in the last two weeks")
        elif updated_days <= 60:
            add(8, "active in the last two months")
        elif updated_days > 365:
            add(-15, "no activity for over a year")
    if created_days is not None and created_days > 730:
        flags.append("old-issue")
        add(-10, "opened more than two years ago")

    # --- Will a PR actually get merged? ------------------------------------
    if health is not None:
        ratio = health.outside_merge_ratio
        outside_total = health.outside_merged + health.outside_closed_unmerged
        if ratio is None:
            if health.closed_sample:
                add(-5, "recent PRs are all from the core team or bots")
        elif outside_total < MIN_OUTSIDE_SAMPLE:
            pass  # too few outside PRs to judge either way
        elif health.outside_merged == 0:
            flags.append("no-outside-merges")
            add(-15, "no recent outside PRs were merged")
        else:
            if ratio >= 0.5:
                add(10, "merges %d%% of recent outside PRs" % round(ratio * 100))
            elif ratio < 0.25:
                add(-5, "merges only %d%% of recent outside PRs" % round(ratio * 100))
            days = health.median_merge_days
            if days is not None and health.outside_merged >= MIN_OUTSIDE_SAMPLE:
                if days <= 7:
                    add(10, "outside PRs merge in ~%s days" % _fmt_days(days))
                elif days <= 30:
                    add(4, "outside PRs merge in ~%s days" % _fmt_days(days))
                elif days > 60:
                    flags.append("slow-merges")
                    add(-8, "outside PRs take ~%s days to merge" % _fmt_days(days))

    # --- Competition and history ------------------------------------------
    if signals is not None:
        if signals.active_claims:
            flags.append("recently-claimed")
            if signals.open_policy:
                add(-5, "recently claimed, but maintainers say just open a PR")
            else:
                add(-25, "%d recent claim(s) by others" % len(signals.active_claims))
        elif signals.stale_claims:
            add(-3, "older claim(s) went quiet")
        if signals.pulls_with_state("closed"):
            flags.append("previous-attempt-closed")
            add(-5, "an earlier PR was closed unmerged; read why first")
        if signals.maintainer_comments:
            add(4, "maintainers have commented")
        if signals.injection_hints:
            # Verdicts are computed here, in code, so planted text cannot make an issue look
            # available. The flag tells the user and any model reading the output to be careful.
            flags.append("suspicious-instructions")

    # --- Is the task clear and the right size? -----------------------------
    labels = {label.lower() for label in candidate.labels}
    if {label.lower() for label in profile.labels} & labels:
        add(5, "labelled for newcomers")
    undecided = sorted(labels & UNDECIDED_LABELS)
    if undecided:
        flags.append("needs-decision")
        add(-15, "labelled %s: needs a decision before code" % ", ".join(undecided))
    if labels & URGENT_LABELS:
        add(-5, "high-priority issues are often picked up by maintainers")
    if candidate.comments <= 5:
        add(5, "short thread")
    elif candidate.comments > 15:
        flags.append("busy-thread")
        add(-10, "long thread (%d comments)" % candidate.comments)
    body_length = len((candidate.body or "").strip())
    if body_length >= 300:
        add(5, "detailed description")
    elif body_length < 40:
        add(-5, "little or no description")

    candidate.effort = estimate_effort(candidate)
    if EFFORT_HOURS[candidate.effort] > profile.hours * 1.5:
        flags.append("may-exceed-time")
        add(-10, "looks %s; you have ~%sh" % (candidate.effort, _fmt_days(profile.hours)))

    candidate.flags = flags
    candidate.reasons = reasons
    candidate.score = max(0, min(100, score))
    if any(flag in SKIP_FLAGS for flag in flags):
        candidate.verdict = "skip"
    elif flags:
        candidate.verdict = "caution"
    else:
        candidate.verdict = "ready"
    return candidate


def _fmt_days(value: float) -> str:
    return ("%.1f" % value).rstrip("0").rstrip(".")
