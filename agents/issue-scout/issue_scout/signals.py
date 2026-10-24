"""Deterministic signal extraction from issue timelines and repository activity.

Nothing here calls a model: every signal is backed by a comment or event the
contributor can open and check.
"""

from __future__ import annotations

import re
import statistics
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from .guardrails import detect_injection
from .models import IssueSignals, Mention, PullRef, RepoHealth

CLAIM_WINDOW_DAYS = 30
MAINTAINER_ROLES = {"OWNER", "MEMBER", "COLLABORATOR"}
OUTSIDE_ROLES = {"NONE", "CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER"}

_CLAIM_PATTERNS = [
    r"\b(can|could|may) i (please )?(work|take|pick|try|tackle|handle)\b",
    r"\bi(?:'d| would) (like|love|be happy|be glad) to (work|take|pick|try|tackle|contribute|implement|fix|help)\b",
    r"\bi(?:'ll| will| am|'m| shall) (be )?(work(ing)?|tak(e|ing)|pick(ing)?|tackl(e|ing)|start(ing)?) (on |up )?(this|it)\b",
    r"\b(please )?assign (this |it |the issue )?(issue )?to me\b",
    r"\bi(?:'m| am) interested (in|to) (work|implement|tak|fix|contribut|solv)",
    r"(^|\s)/(assign|take|claim)\b",
    r"^\s*(i'?m |i am )?working on (this|it)\b",
    r"\blet me (give|take) (this|it) a (shot|try|stab|go)\b",
    r"\bdibs\b",
]
_RESOLVED_PATTERNS = [
    r"\balready (exists|been (fixed|implemented|resolved|addressed|merged|done)|fixed|implemented|resolved|addressed|supported|done)\b",
    r"\b(fixed|resolved|addressed|implemented|closed) (in|by|via) (#\d+|https?://\S+|[0-9a-f]{7,40}\b)",
    r"\bduplicate of #?\d+",
    r"\b(this|it) (can|should) (now )?be closed\b(?! off| once| after| when| if| with)",
    r"\bno longer (needed|relevant|reproducible|an issue|applies)\b",
    r"\b(was|been|got) (done|fixed|implemented|added|resolved) in (the |a )?(last|latest|recent|new|newest|previous) (release|version|update)\b",
    r"\bclosing (this )?(as|since|because)\b",
]
# A resolved-looking phrase right after one of these is a denial ("not fixed in #12").
_NEGATION_BEFORE = re.compile(r"\b(not|n't|never|no)\b[\w ']{0,6}$", re.IGNORECASE)
_OPEN_POLICY_PATTERNS = [
    r"\bno (need for )?assign(ment|ing|ees?)\b",
    r"\b(don'?t|do not|we don'?t) (need to )?assign\b",
    r"\bno need to (ask|be assigned|wait)\b",
    r"\bjust (open|submit|send|raise|create) (a |the )?(pr|pull request)\b",
    r"\bfeel free to (open|submit|send|pick|work|take|go ahead)\b",
    r"\bfirst (pr|pull request) (wins|gets merged|to be merged)\b",
]

_claim_re = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _CLAIM_PATTERNS]
_resolved_re = [re.compile(p, re.IGNORECASE) for p in _RESOLVED_PATTERNS]
_policy_re = [re.compile(p, re.IGNORECASE) for p in _OPEN_POLICY_PATTERNS]


def parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def days_between(earlier: Optional[str], now: datetime) -> Optional[float]:
    start = parse_time(earlier)
    if start is None:
        return None
    return (now - start).total_seconds() / 86400.0


def _strip_quotes(text: str) -> str:
    """Drop quoted replies ("> ...") so we judge what the commenter wrote themselves."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))


def _first_match(patterns: Iterable[re.Pattern], text: str) -> Optional[str]:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return _snippet(text, match.start(), match.end())
    return None


def _snippet(text: str, start: int, end: int, width: int = 60) -> str:
    left = max(0, start - width)
    right = min(len(text), end + width)
    snippet = " ".join(text[left:right].split())
    return ("..." if left > 0 else "") + snippet + ("..." if right < len(text) else "")


def detect_claim(text: str) -> Optional[str]:
    return _first_match(_claim_re, _strip_quotes(text or ""))


def detect_resolved(text: str) -> Optional[str]:
    """Ignore denials ("not fixed in #12") and questions ("is this already fixed?")."""
    text = _strip_quotes(text or "")
    for pattern in _resolved_re:
        for match in pattern.finditer(text):
            if _NEGATION_BEFORE.search(text[max(0, match.start() - 20) : match.start()]):
                continue
            sentence_end = re.search(r"[.!?\n]", text[match.end() :])
            if sentence_end and sentence_end.group() == "?":
                continue
            return _snippet(text, match.start(), match.end())
    return None


def detect_open_policy(text: str) -> Optional[str]:
    return _first_match(_policy_re, _strip_quotes(text or ""))


def _login(user: Optional[dict]) -> str:
    return (user or {}).get("login", "") or ""


def _is_bot(user: Optional[dict]) -> bool:
    user = user or {}
    return user.get("type") == "Bot" or _login(user).endswith("[bot]")


def analyze_timeline(timeline: List[dict], repo: str, assignees: List[str], now: datetime) -> IssueSignals:
    """Turn raw timeline events into the signals a contributor cares about."""
    signals = IssueSignals(assignees=list(assignees))
    seen_pulls = set()

    for event in timeline:
        kind = event.get("event")

        if kind == "commented":
            user = event.get("user") or event.get("actor")
            if _is_bot(user):
                continue
            author = _login(user)
            role = event.get("author_association", "NONE")
            is_maintainer = role in MAINTAINER_ROLES
            body = event.get("body") or ""
            created = event.get("created_at", "")
            url = event.get("html_url", "")

            if is_maintainer:
                signals.maintainer_comments += 1
                signals.last_maintainer_comment = created
                policy = detect_open_policy(body)
                if policy:
                    signals.open_policy = Mention(author, created, url, policy, True)

            claim = detect_claim(body)
            if claim:
                mention = Mention(author, created, url, claim, is_maintainer)
                age = days_between(created, now)
                if age is not None and age <= CLAIM_WINDOW_DAYS:
                    signals.active_claims.append(mention)
                else:
                    signals.stale_claims.append(mention)

            resolved = detect_resolved(body)
            if resolved:
                signals.resolved_hints.append(Mention(author, created, url, resolved, is_maintainer))

            injection = detect_injection(body)
            if injection:
                signals.injection_hints.append(Mention(author, created, url, injection, is_maintainer))

        elif kind == "cross-referenced":
            source = (event.get("source") or {}).get("issue") or {}
            pull = source.get("pull_request")
            source_repo = (source.get("repository") or {}).get("full_name", "")
            if not pull or (source_repo and source_repo.lower() != repo.lower()):
                continue
            number = source.get("number")
            if number in seen_pulls:
                continue
            seen_pulls.add(number)
            if source.get("state") == "open":
                state = "open"
            elif pull.get("merged_at"):
                state = "merged"
            else:
                state = "closed"
            signals.pulls.append(
                PullRef(number, source.get("html_url", ""), source.get("title", ""), state, _login(source.get("user")))
            )

    return signals


def repo_health(repo: dict, closed_pulls: List[dict]) -> RepoHealth:
    """Summarise how this repository treats PRs from people outside the core team."""
    health = RepoHealth(
        full_name=repo.get("full_name", ""),
        stars=repo.get("stargazers_count", 0),
        pushed_at=repo.get("pushed_at", ""),
        archived=bool(repo.get("archived")),
        description=repo.get("description") or "",
        default_branch=repo.get("default_branch") or "main",
    )
    merge_days = []
    health.closed_sample = len(closed_pulls)
    for pull in closed_pulls:
        if _is_bot(pull.get("user")) or pull.get("author_association") not in OUTSIDE_ROLES:
            continue
        created, merged = parse_time(pull.get("created_at")), parse_time(pull.get("merged_at"))
        if merged and created:
            health.outside_merged += 1
            merge_days.append((merged - created).total_seconds() / 86400.0)
        else:
            health.outside_closed_unmerged += 1
    if merge_days:
        health.median_merge_days = round(statistics.median(merge_days), 1)
    return health
