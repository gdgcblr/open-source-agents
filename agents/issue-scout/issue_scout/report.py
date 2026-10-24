"""Markdown rendering. Reads fine in a terminal and pastes cleanly into GitHub."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from .models import CAUTION_FLAGS, SKIP_FLAGS, SKIP_SUMMARY, Candidate, ScoutResult
from .scoring import MIN_OUTSIDE_SAMPLE
from .signals import days_between

VERDICT_LABEL = {"ready": "READY", "caution": "CAUTION", "skip": "SKIP", "unknown": "?"}


def _ago(timestamp: str, now: datetime) -> str:
    days = days_between(timestamp, now)
    if days is None:
        return "unknown"
    if days < 1:
        return "today"
    if days < 60:
        return "%d days ago" % days
    if days < 730:
        return "%d months ago" % (days // 30)
    return "%d years ago" % (days // 365)


def _stars(count: int) -> str:
    return "%.1fk" % (count / 1000.0) if count >= 1000 else str(count)


def evidence(candidate: Candidate, now: datetime) -> List[str]:
    """One line per flag, each pointing at the comment or PR that caused it."""
    lines: List[str] = []
    signals = candidate.signals
    for flag in candidate.flags:
        label = SKIP_FLAGS.get(flag) or CAUTION_FLAGS.get(flag) or flag
        proof = ""
        if signals is not None:
            if flag == "assigned":
                proof = ", ".join("@" + name for name in signals.assignees)
            elif flag in ("open-pr", "merged-pr", "previous-attempt-closed"):
                state = {"open-pr": "open", "merged-pr": "merged", "previous-attempt-closed": "closed"}[flag]
                proof = ", ".join("#%d %s" % (p.number, p.url) for p in signals.pulls_with_state(state))
            elif flag == "recently-claimed":
                proof = "; ".join("@%s %s %s" % (m.author, _ago(m.created_at, now), m.url) for m in signals.active_claims[:3])
            elif flag in ("likely-resolved", "possibly-resolved"):
                hint = signals.resolved_hints[-1]
                proof = '@%s: "%s" %s' % (hint.author, hint.quote, hint.url)
        lines.append("%s%s" % (label, (" -> " + proof) if proof else ""))
    if signals is not None and signals.open_policy and "recently-claimed" in candidate.flags:
        policy = signals.open_policy
        lines.append('maintainer @%s: "%s" %s' % (policy.author, policy.quote, policy.url))
    return lines


def _repo_line(candidate: Candidate) -> str:
    health = candidate.repo_health
    if health is None:
        return ""
    parts = ["%s stars" % _stars(health.stars)]
    outside = health.outside_merged + health.outside_closed_unmerged
    if outside >= MIN_OUTSIDE_SAMPLE:
        parts.append("merges %d%% of recent outside PRs" % round(health.outside_merge_ratio * 100))
    elif outside:
        parts.append("only %d of the last %d closed PRs came from outside contributors" % (outside, health.closed_sample))
    elif health.closed_sample:
        parts.append("last %d closed PRs were all from the core team or bots" % health.closed_sample)
    if health.median_merge_days is not None and health.outside_merged >= MIN_OUTSIDE_SAMPLE:
        parts.append("median %s days to merge" % ("%.1f" % health.median_merge_days).rstrip("0").rstrip("."))
    return ", ".join(parts)


def render_candidate(candidate: Candidate, now: datetime, index: Optional[int] = None) -> str:
    prefix = "%d. " % index if index is not None else ""
    badge = VERDICT_LABEL[candidate.verdict]
    if candidate.verdict != "skip":
        badge += " %d" % candidate.score
    lines = [
        "%s**[%s]** [%s](%s) %s" % (prefix, badge, candidate.ref, candidate.url, candidate.title),
        "   - effort: %s (rough guess) | updated %s | %d comments | labels: %s"
        % (candidate.effort, _ago(candidate.updated_at, now), candidate.comments, ", ".join(candidate.labels) or "none"),
    ]
    repo_line = _repo_line(candidate)
    if repo_line:
        lines.append("   - repo: " + repo_line)
    for line in evidence(candidate, now):
        lines.append("   - ! " + line)
    good = [r for r in candidate.reasons if r.startswith("+")]
    if good:
        lines.append("   - why: " + "; ".join(r[r.index(" ") + 1 :] for r in good[:4]))
    return "\n".join(lines)


def render_find(result: ScoutResult, now: datetime, show_skipped: bool = False) -> str:
    profile = result.profile
    who = ", ".join(profile.languages) or "any language"
    if profile.topics:
        who += " | topics: " + ", ".join(profile.topics)
    out = ["## Issue Scout: %d picks for %s, ~%sh" % (len(result.candidates), who, ("%.1f" % profile.hours).rstrip("0").rstrip(".")), ""]
    if not result.candidates:
        out.append("No issues passed the checks. Try more languages, a lower --min-stars, or --label \"help wanted\".")
    for i, candidate in enumerate(result.candidates, 1):
        out.append(render_candidate(candidate, now, i))
        out.append("")

    summary = result.skip_summary()
    if summary:
        parts = ["%d %s" % (count, SKIP_SUMMARY[flag]) for flag, count in sorted(summary.items(), key=lambda kv: -kv[1])]
        out.append("**Filtered out %d dead ends** that GitHub search still listed: %s." % (len(result.skipped), ", ".join(parts)))
    if show_skipped and result.skipped:
        out.append("")
        out.append("### Skipped")
        for candidate in result.skipped:
            out.append(render_candidate(candidate, now))
    out.append("")
    out.append("_Checked %d repos with %d GitHub API calls._" % (result.repos_considered, result.requests_made))
    for note in result.notes:
        out.append("_Note: %s_" % note)
    return "\n".join(out).rstrip() + "\n"


def render_related(related: Dict[str, list]) -> str:
    out = []
    titles = {"open_issues": "Open related issues", "closed_issues": "Closed related issues", "merged_prs": "Merged PRs on the same topic"}
    for key, title in titles.items():
        items = related.get(key) or []
        out.append("### %s" % title)
        if not items:
            out.append("- none found")
        for item in items:
            item = item if isinstance(item, dict) else vars(item)
            dup = " **(possible duplicate)**" if item.get("possible_duplicate") else ""
            out.append("- [#%d](%s) %s%s" % (item["number"], item["url"], item["title"], dup))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_brief(facts: Dict[str, object], now: datetime, ai: Optional[Dict[str, object]] = None) -> str:
    issue = facts["issue"]
    conventions = facts["conventions"]
    out = ["## Starter brief: [%s](%s) %s" % (issue["ref"], issue["url"], issue["title"]), ""]
    out.append("**Verdict:** %s (score %d) | effort: %s (rough guess)" % (VERDICT_LABEL[issue["verdict"]], issue["score"], issue["effort"]))
    for line in facts.get("evidence") or []:
        out.append("- ! " + line)
    out.append("")

    if ai:
        out.append("### Summary (%s)" % ai.get("model", "Gemini"))
        out.append(str(ai.get("summary", "")))
        out.append("")
        if ai.get("suggested_approach"):
            out.append("### Suggested approach (Gemini, verify before coding)")
            for i, step in enumerate(ai["suggested_approach"], 1):
                out.append("%d. %s" % (i, step))
            out.append("")
        if ai.get("questions_for_maintainers"):
            out.append("### Questions worth asking first")
            for question in ai["questions_for_maintainers"]:
                out.append("- " + question)
            out.append("")
        if ai.get("risks"):
            out.append("### Risks")
            for risk in ai["risks"]:
                out.append("- " + risk)
            out.append("")

    out.append("### Where to look")
    files = (ai or {}).get("likely_files") or facts.get("likely_files") or []
    if not files:
        out.append("- no confident file matches; search the repo for: " + ", ".join(facts.get("keywords") or []))
    for entry in files:
        out.append("- `%s` - %s" % (entry["path"], entry.get("why", "")))
    out.append("")

    out.append("### Prior work")
    out.append(render_related(facts["related"]).replace("### ", "#### "))

    out.append("### House rules")
    if conventions.get("contributing_url"):
        out.append("From [the contributing guide](%s):" % conventions["contributing_url"])
    else:
        out.append("- No CONTRIBUTING guide found; follow the README and match existing code style.")
    for rule in conventions.get("rules", []):
        out.append("- " + rule["advice"])
    for name, key in (("Setup", "setup_commands"), ("Test", "test_commands"), ("Lint", "lint_commands")):
        commands = conventions.get(key) or []
        if commands:
            out.append("- %s: %s" % (name, " | ".join("`%s`" % c for c in commands)))
    return "\n".join(out).rstrip() + "\n"
