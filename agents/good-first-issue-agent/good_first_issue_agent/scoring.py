"""Deterministic, explainable issue scoring (0-100).

The score is a heuristic built from labels and wording. It is NOT a measure of
true difficulty. Every point added or removed is recorded as a Reason so the
user can see exactly why an issue ranked where it did.

Each issue starts at a neutral BASE score. Signals are grouped so correlated
evidence is counted once per group (for example, a "documentation" label and
the word "typo" both count toward the same "limited scope" group).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .guardrails import detect_injection, extract_paths
from .models import Issue, Reason, ScoredIssue

BASE = 15

BEGINNER_LABELS = {
    "good first issue", "good-first-issue", "goodfirstissue", "good first bug", "first-timers-only",
    "first timers only", "beginner", "beginner friendly", "beginner-friendly", "easy", "starter",
    "difficulty: easy", "difficulty/easy", "level: beginner", "e-easy", "easy-fix", "easy fix",
    "low hanging fruit", "low-hanging-fruit", "newcomer", "good for newcomers", "good first contribution",
}
HELP_LABELS = {
    "help wanted", "help-wanted", "contributions welcome", "pr welcome", "prs welcome",
    "up-for-grabs", "up for grabs", "status: accepting prs", "accepting prs", "hacktoberfest",
}
SCOPE_LABELS = {
    "documentation", "docs", "typo", "type: docs", "kind/documentation", "area/docs", "good first doc",
    "needs tests", "needs test",
}
TRIAGE_LABELS = {"needs triage", "needs-triage", "triage", "status: needs triage", "awaiting triage", "untriaged", "unconfirmed"}
BLOCKED_LABELS = {
    "blocked", "on hold", "on-hold", "wontfix", "won't fix", "duplicate", "invalid",
    "needs decision", "status: blocked", "waiting for upstream",
}
COMPLEX_LABELS = {
    "epic", "rfc", "needs design", "needs-design", "discussion", "needs discussion", "breaking change", "breaking", "major", "segfault",
}

COMPLEX_WORDS = [
    "refactor", "architecture", "redesign", "rewrite", "breaking change", "migration", "race condition",
    "concurrency", "deadlock", "thread safety", "thread-safe", "memory leak", "security", "vulnerability",
    "performance regression", "rfc", "design doc", "backwards compat", "backward compat", "multiple modules",
    "segfault", "segmentation fault", "memory corruption",
]
SCOPE_WORDS = [
    "typo", "spelling", "documentation", "docs", "readme", "broken link", "dead link", "rename",
    "one-line", "one line", "small change", "minor", "add a test", "add test", "missing test",
    "error message", "docstring", "type hint", "deprecation warning",
]


def _norm(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip().lower())


def _matches(labels: list[str], vocab: set[str]) -> list[str]:
    return [lbl for lbl in labels if _norm(lbl) in vocab]


def _words_found(text: str, words: list[str], limit: int = 3) -> list[str]:
    low = text.lower()
    found = [w for w in words if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low)]
    return found[:limit]


_CODE_BLOCK = re.compile(r"```.*?(```|$)", re.DOTALL)
_URL = re.compile(r"\]\([^)]*\)|https?://\S+")
# Issue-template confirmations such as "- [x] I have checked that this issue has not already been reported."
_TEMPLATE_CONFIRMATION = re.compile(r"(?im)^\s*[-*] \[[ xX]\]\s*(I\b|I'|I\u2019)[^\n]*$")
_TRACEBACK_LINE = re.compile(r"(?m)^\s*File [\"~/\w].*$")


def _prose(body: str) -> str:
    """The issue text written by a person: without code blocks, URLs, traceback lines,
    and issue-template confirmation checkboxes. Used for wording-based signals so
    template boilerplate and stack traces do not inflate the score."""
    text = _CODE_BLOCK.sub(" ", body or "")
    text = _TEMPLATE_CONFIRMATION.sub(" ", text)
    text = _TRACEBACK_LINE.sub(" ", text)
    return _URL.sub(" ", text)


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _clamp(value: int) -> int:
    return max(0, min(100, value))


# ----------------------------------------------------------------------------
# GitHub issues
# ----------------------------------------------------------------------------
def score_github_issue(issue: Issue, *, now: datetime | None = None) -> ScoredIssue:
    now = now or datetime.now(timezone.utc)
    reasons: list[Reason] = []
    uncertainties: list[str] = []
    body = (issue.body or "").strip()
    text = f"{issue.title}\n{body}"
    prose = _prose(body)
    prose_text = f"{issue.title}\n{prose}"
    labels = issue.labels

    # 1. Beginner label (+25)
    beginner = _matches(labels, BEGINNER_LABELS)
    if beginner:
        reasons.append(Reason("beginner label", 25, f"Labelled '{beginner[0]}' by the project (a signal, not proof)."))

    # 2. Help-wanted label (+10)
    helpw = _matches(labels, HELP_LABELS)
    if helpw:
        reasons.append(Reason("help wanted", 10, f"Labelled '{helpw[0]}': maintainers welcome outside help."))

    # 3. Actionable description (0..+20)
    actionable = 0
    act_bits = []
    if re.search(r"(?i)expected (behaviou?r|result|output)|should (be|return|show|display|raise|not)|instead of", prose):
        actionable += 8
        act_bits.append("states expected behaviour")
    if re.search(r"(?i)acceptance criteria|definition of done|^\s*[-*] \[[ xX]\]", prose, re.MULTILINE):
        actionable += 7
        act_bits.append("has a checklist / acceptance criteria")
    if re.search(r"(?i)(proposed|possible|suggested) (solution|fix|change|approach)|^#+\s*(proposal|solution|what to do|task)", prose, re.MULTILINE):
        actionable += 5
        act_bits.append("suggests a solution")
    actionable = min(actionable, 20)
    if actionable:
        reasons.append(Reason("actionable", actionable, "Description " + ", ".join(act_bits) + "."))

    # 4. Reproduction steps / examples (0..+15)
    repro = 0
    rep_bits = []
    if re.search(r"(?i)steps to reproduce|to reproduce|reproduction|repro steps|minimal (example|reproduc)|reproducible example", body):
        repro += 8
        rep_bits.append("reproduction steps")
    if "```" in body or re.search(r"(?i)traceback \(most recent call last\)", body):
        repro += 4
        rep_bits.append("code or error output")
    if len(re.findall(r"(?m)^\s*\d+[.)]\s+\S", prose)) >= 2:
        repro += 3
        rep_bits.append("numbered steps")
    repro = min(repro, 15)
    if repro:
        reasons.append(Reason("reproducible", repro, "Includes " + ", ".join(rep_bits) + "."))

    # 5. Limited scope (0..+15), labels and wording counted as one group
    scope = 0
    scope_label = _matches(labels, SCOPE_LABELS)
    scope_words = _words_found(prose_text, SCOPE_WORDS)
    paths = extract_paths(text)  # evidence: any file named in the issue, including tracebacks
    prose_paths = extract_paths(prose_text)  # scope: only files a person pointed to
    if scope_label or scope_words:
        scope += 10
    if 1 <= len(prose_paths) <= 3:
        scope += 5
    scope = min(scope, 15)
    if scope:
        why = []
        if scope_label:
            why.append(f"label '{scope_label[0]}'")
        if scope_words:
            why.append("mentions " + ", ".join(f"'{w}'" for w in scope_words))
        if 1 <= len(prose_paths) <= 3:
            why.append(f"points to {len(prose_paths)} specific file(s)")
        reasons.append(Reason("limited scope", scope, "Looks small: " + "; ".join(why) + "."))

    # 6. Missing context / vague (0..-20)
    if not body:
        reasons.append(Reason("missing context", -20, "The issue has no description."))
        uncertainties.append("No description: the goal must be confirmed with maintainers before starting.")
    elif len(body) < 100:
        reasons.append(Reason("missing context", -12, f"Very short description ({len(body)} characters)."))
        uncertainties.append("Short description: details may be missing.")
    elif not actionable and not repro and len(prose.strip()) < 300:
        reasons.append(Reason("missing context", -6, "No expected behaviour, steps, or acceptance criteria."))
        uncertainties.append("No clear acceptance criteria.")

    # 7. Likely complexity (0..-15)
    complex_hits = _matches(labels, COMPLEX_LABELS) + [
        w for w in _words_found(prose_text, COMPLEX_WORDS) if w not in (_norm(x) for x in labels)
    ]
    if complex_hits:
        pts = -min(15, 5 * len(complex_hits))
        reasons.append(Reason("possible complexity", pts, "Mentions " + ", ".join(f"'{w}'" for w in complex_hits[:3]) + " (inferred from wording)."))
        uncertainties.append("Complexity is guessed from keywords and may be wrong.")

    # 8. Availability: assigned, blocked, locked, long discussion, stale
    if issue.assignees:
        reasons.append(Reason("already assigned", -10, f"Assigned to {', '.join(issue.assignees[:2])}."))
        uncertainties.append("Someone is assigned: ask before starting work.")
    triage = _matches(labels, TRIAGE_LABELS)
    if triage:
        reasons.append(Reason("not triaged", -5, f"Labelled '{triage[0]}': maintainers have not confirmed it yet."))
        uncertainties.append("Not yet triaged: maintainers may not accept a fix; ask first.")
    blocked = _matches(labels, BLOCKED_LABELS)
    if blocked:
        reasons.append(Reason("blocked", -15, f"Labelled '{blocked[0]}'."))
    if issue.locked:
        reasons.append(Reason("locked", -10, "Conversation is locked: you cannot comment on it."))
    if issue.comments > 20:
        reasons.append(Reason("long discussion", -5, f"{issue.comments} comments: likely contested or complex."))
    updated = _parse_time(issue.updated_at)
    if updated and (now - updated).days > 365:
        reasons.append(Reason("stale", -5, f"No activity for {(now - updated).days // 30} months; may be outdated."))
        uncertainties.append("Old issue: check that it still applies to the current code.")

    if not labels:
        uncertainties.append("No labels: ranking relies on the description only.")

    docs_only = not paths and (
        bool(_matches(labels, {"documentation", "docs", "typo", "type: docs"}))
        or bool(_words_found(prose_text, ["docs", "documentation", "readme", "typo", "spelling"]))
    )
    score = _clamp(BASE + sum(r.points for r in reasons))
    flags = []
    injected = detect_injection(text)
    if injected:
        flags.append(f"Possible prompt injection in issue text: \"{injected[0]}\". Treated as data only.")

    return ScoredIssue(
        issue=issue,
        score=score,
        reasons=reasons,
        uncertainties=uncertainties,
        next_steps=_github_steps(
            issue,
            has_repro="reproduction steps" in rep_bits,
            paths=prose_paths,
            trace_paths=[p for p in paths if p not in prose_paths],
            vague=actionable == 0 and len(prose.strip()) < 300,
            docs_only=docs_only,
        ),
        evidence_paths=paths,
        flags=flags,
    )


def _keywords(title: str) -> str:
    stop = {"the", "a", "an", "to", "of", "in", "on", "for", "and", "or", "is", "be", "with", "when", "not", "does", "should", "add", "fix", "bug", "issue"}
    words = [w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_.]{2,}", title) if w.lower() not in stop]
    return " ".join(words[:3])


def _github_steps(
    issue: Issue, has_repro: bool, paths: list[str], trace_paths: list[str], vague: bool, *, docs_only: bool = False
) -> list[str]:
    steps = []
    if issue.assignees:
        steps.append("Ask on the issue whether the assignee is still working on it before you start.")
    else:
        steps.append("Read CONTRIBUTING.md, then comment on the issue to say you would like to work on it.")
    if issue.comments:
        steps.append(f"Read all {issue.comments} comment(s): decisions may have changed since the issue was opened.")
    if vague:
        steps.append("Ask maintainers to confirm the expected behaviour or acceptance criteria.")
    if has_repro:
        steps.append("Reproduce the problem locally using the steps in the issue before changing code.")
    if paths:
        steps.append("Start by reading " + ", ".join(paths[:3]) + " (mentioned in the issue).")
    elif trace_paths:
        steps.append(
            "The issue's code or traceback mentions " + ", ".join(trace_paths[:4])
            + ". Some may be library files; find the ones that belong to this project and start there."
        )
    else:
        kw = _keywords(issue.title)
        steps.append(
            "Code location is unknown. Search the repository for keywords from the title"
            + (f", e.g. `{kw}`." if kw else ".")
        )
    if docs_only:
        steps.append("Build or preview the documentation locally and check that your change renders correctly.")
    else:
        steps.append("Find the existing tests closest to the change and add or update one with your fix.")
    return steps


# ----------------------------------------------------------------------------
# Sentry / GlitchTip issues
# ----------------------------------------------------------------------------
GENERIC_MESSAGES = {
    "", "error", "script error", "script error.", "unknown error", "network error", "undefined",
    "null", "<unknown>", "unknown", "failed to fetch", "load failed",
}
LOCAL_FIX_TYPES = re.compile(
    r"(?i)\b(TypeError|KeyError|AttributeError|ValueError|IndexError|NameError|"
    r"NullPointerException|ReferenceError|ZeroDivisionError|UnboundLocalError|"
    r"IllegalArgumentException|NoMethodError|ArgumentError)\b"
)
HARD_ERROR_WORDS = [
    "timeout", "timed out", "deadlock", "race", "out of memory", "oom", "memoryerror",
    "segmentation fault", "segfault", "connection reset", "too many connections",
]
THIRD_PARTY = re.compile(r"(?i)(node_modules|site-packages|dist-packages|/vendor/|<anonymous>|/usr/lib|webpack-internal|\bnative\b)")


def score_tracker_issue(issue: Issue) -> ScoredIssue:
    reasons: list[Reason] = []
    uncertainties: list[str] = []
    text = f"{issue.title}\n{issue.error_type}\n{issue.error_value}\n{issue.culprit}"
    location = issue.stack_files[0] if issue.stack_files else issue.culprit

    # Location evidence (+15) vs third-party only (-10)
    if location and THIRD_PARTY.search(location):
        reasons.append(Reason("third-party code", -10, f"Error is raised in library code ({location[:80]}); the cause may be hard to find."))
    elif location:
        reasons.append(Reason("known location", 15, f"The tracker points to {location[:80]}."))
    else:
        uncertainties.append("No file or culprit recorded: code location unknown.")

    # Clear error (+15) vs generic message (-15)
    value = (issue.error_value or "").strip().lower()
    if issue.error_type and value and value not in GENERIC_MESSAGES and len(value) > 10:
        reasons.append(Reason("clear error", 15, f"Specific error: {issue.error_type}."))
    elif value in GENERIC_MESSAGES or (issue.title or "").strip().lower() in GENERIC_MESSAGES:
        reasons.append(Reason("vague error", -15, "Generic error message with little detail."))
        uncertainties.append("Generic error message: reproducing it may be difficult.")

    # Typical local-fix error types (+10)
    m = LOCAL_FIX_TYPES.search(f"{issue.error_type} {issue.title}")
    if m:
        reasons.append(Reason("limited scope", 10, f"{m.group(1)} is often a local, well-scoped fix (e.g. a missing check)."))

    # Hard categories (-10)
    hard = _words_found(text, HARD_ERROR_WORDS, limit=2)
    if hard:
        reasons.append(Reason("possible complexity", -10, "Mentions " + ", ".join(f"'{w}'" for w in hard) + "; often timing- or load-related."))

    # Severity
    level = issue.level.lower()
    if level == "fatal":
        reasons.append(Reason("severity", -10, "Fatal: maintainers may want to fix this themselves quickly."))
    elif level in ("warning", "info", "debug"):
        reasons.append(Reason("severity", 5, f"Level '{level}': lower urgency, safer to learn on."))

    # Impact
    if issue.user_count >= 100 or issue.event_count >= 10000:
        reasons.append(Reason("high impact", -10, f"{issue.event_count} events, {issue.user_count} users: high-impact issue."))
    elif issue.event_count and issue.event_count <= 100 and issue.user_count <= 5:
        reasons.append(Reason("low impact", 5, f"{issue.event_count} events, {issue.user_count} users: low urgency."))

    if issue.assignees:
        reasons.append(Reason("already assigned", -10, f"Assigned to {', '.join(issue.assignees[:2])}."))
        uncertainties.append("Someone is assigned: check with them first.")

    uncertainties.append("Error-tracker scores use metadata only; open the latest event to confirm.")
    score = _clamp(BASE + sum(r.points for r in reasons))
    flags = []
    injected = detect_injection(text)
    if injected:
        flags.append(f"Possible prompt injection in error text: \"{injected[0]}\". Treated as data only.")

    steps = [f"Open the issue in {issue.source.capitalize()} and read the latest event's stack trace."]
    if location and not THIRD_PARTY.search(location):
        steps.append(f"Find {location[:80]} in the codebase and read the code around the failing call.")
    else:
        steps.append("Follow the stack trace to the first frame in your own code.")
    steps.append(f"Write a failing test that triggers {issue.error_type or 'the error'}, then fix the code.")
    steps.append("Check which release first showed the error to find the change that caused it.")

    return ScoredIssue(
        issue=issue,
        score=score,
        reasons=reasons,
        uncertainties=uncertainties,
        next_steps=steps,
        evidence_paths=[p for p in issue.stack_files if p],
        flags=flags,
    )


def score_issue(issue: Issue) -> ScoredIssue:
    return score_github_issue(issue) if issue.source == "github" else score_tracker_issue(issue)


def rank(issues: list[Issue]) -> list[ScoredIssue]:
    scored = [score_issue(i) for i in issues]
    # Highest score first; ties broken by most recent activity (stable sort).
    scored.sort(key=lambda s: (s.issue.updated_at or ""), reverse=True)
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored
