"""The scouting pipeline: healthy repos -> open beginner issues -> evidence -> ranked shortlist."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from . import conventions as conv
from .github import GitHubClient, GitHubError, RateLimitError, parse_issue_url
from .guardrails import check_repo, check_user, clamp, clean_profile, detect_injection
from .models import Candidate, IssueSignals, Mention, Profile, ScoutResult
from .related import find_related, keywords
from .report import evidence
from .scoring import evaluate
from .signals import analyze_timeline, days_between, repo_health

REPO_ACTIVE_DAYS = 30
ISSUE_ACTIVE_DAYS = 365
REPOS_PER_QUERY = 6
MAX_REPO_QUERIES = 4
MAX_ISSUE_QUERIES = 3
MAX_PER_REPO = 2
WORKERS = 6


class Scout:
    def __init__(self, client: Optional[GitHubClient] = None, now: Optional[datetime] = None):
        self.client = client or GitHubClient()
        self.now = now or datetime.now(timezone.utc)
        self._health: Dict[str, object] = {}

    # --- Profile -------------------------------------------------------------

    def profile_from_user(self, user: str, **overrides) -> Profile:
        """Guess languages (and frequent topics) from a GitHub user's own recent repos."""
        languages: Counter = Counter()
        topics: Counter = Counter()
        for repo in self.client.user_repos(check_user(user)):
            if repo.get("fork"):
                continue
            age = days_between(repo.get("pushed_at"), self.now)
            if age is not None and age > 730:
                continue
            if repo.get("language"):
                languages[repo["language"].lower()] += 1
            topics.update(repo.get("topics") or [])
        profile = Profile(
            languages=[lang for lang, _ in languages.most_common(3)],
            topics=[topic for topic, count in topics.most_common(2) if count >= 2],
        )
        for key, value in overrides.items():
            if value not in (None, [], ""):
                setattr(profile, key, value)
        return profile

    # --- Find ----------------------------------------------------------------

    def find(self, profile: Profile, limit: int = 5, max_candidates: Optional[int] = None) -> ScoutResult:
        clean_profile(profile)
        limit = int(clamp(limit, 1, 20))
        notes: List[str] = []
        if max_candidates is None:
            max_candidates = 25 if self.client.authenticated else 10
        if not self.client.authenticated:
            notes.append("No GITHUB_TOKEN set: checked fewer issues to stay inside GitHub's anonymous rate limit.")

        repos: Dict[str, dict] = {}
        try:
            repos = self._find_repos(profile)
        except RateLimitError as exc:
            notes.append(str(exc) + " Results are partial.")
        issues = self._find_issues(profile, list(repos), notes)

        # Cheap pre-ranking on search data only, so the API budget goes to the best leads.
        shortlist = sorted(issues, key=self._prescore, reverse=True)[:max_candidates]

        evaluated: List[Candidate] = []
        failures: List[str] = []
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            # Phase 1: one health lookup per repo. Phase 2: one timeline per issue.
            repo_names = sorted({_repo_from_issue(issue) for issue in shortlist})
            health_jobs = {name: pool.submit(self._repo_health, name, repos.get(name)) for name in repo_names}
            for name, job in health_jobs.items():
                try:
                    job.result()
                except GitHubError as exc:
                    failures.append(str(exc) if isinstance(exc, RateLimitError) else "Skipped %s: %s" % (name, exc))
            jobs = [pool.submit(self._enrich, issue, profile) for issue in shortlist if _repo_from_issue(issue) in self._health]
            for job in jobs:
                try:
                    evaluated.append(job.result())
                except GitHubError as exc:
                    failures.append(str(exc) if isinstance(exc, RateLimitError) else "Skipped an issue: %s" % exc)
        for failure in dict.fromkeys(failures):  # de-duplicate, keep order
            notes.append(failure + (" Some issues were not checked." if "rate limit" in failure else ""))

        good = sorted((c for c in evaluated if c.verdict != "skip"), key=lambda c: -c.score)
        skipped = [c for c in evaluated if c.verdict == "skip"]
        return ScoutResult(profile, good[:limit], skipped, len(repos), self.client.requests_made, notes)

    def _find_repos(self, profile: Profile) -> Dict[str, dict]:
        pushed_after = (self.now - timedelta(days=REPO_ACTIVE_DAYS)).strftime("%Y-%m-%d")
        stars = "stars:>=%d" % profile.min_stars
        if profile.max_stars:
            stars = "stars:%d..%d" % (profile.min_stars, profile.max_stars)
        labels = [label.lower() for label in profile.labels]
        issue_count = "good-first-issues:>=2" if "good first issue" in labels else "help-wanted-issues:>=2"
        base = "%s pushed:>%s archived:false is:public mirror:false %s" % (stars, pushed_after, issue_count)

        queries = []
        for language in profile.languages[:3] or [None]:
            for topic in profile.topics[:2] or [None]:
                parts = [base]
                if language:
                    parts.append('language:"%s"' % language)
                if topic:
                    parts.append("topic:%s" % topic)
                queries.append(" ".join(parts))

        repos: Dict[str, dict] = {}
        for query in queries[:MAX_REPO_QUERIES]:
            # Sorting by help-wanted count favours repos that actively ask outsiders for help,
            # instead of the biggest (and most contested) projects.
            for repo in self.client.search_repositories(query, per_page=20, sort="help-wanted-issues"):
                repos.setdefault(repo["full_name"], repo)
        return repos

    def _find_issues(self, profile: Profile, repo_names: List[str], notes: List[str]) -> List[dict]:
        updated_after = (self.now - timedelta(days=ISSUE_ACTIVE_DAYS)).strftime("%Y-%m-%d")
        label_filter = "label:" + ",".join('"%s"' % label for label in profile.labels)
        found: List[dict] = []
        per_repo: Counter = Counter()
        for start in range(0, min(len(repo_names), REPOS_PER_QUERY * MAX_ISSUE_QUERIES), REPOS_PER_QUERY):
            batch = repo_names[start : start + REPOS_PER_QUERY]
            query = "is:issue is:open no:assignee -linked:pr archived:false updated:>%s %s %s" % (
                updated_after,
                label_filter,
                " ".join("repo:" + name for name in batch),
            )
            try:
                results = self.client.search_issues(query, per_page=30, sort="updated")
            except RateLimitError as exc:
                notes.append(str(exc) + " Searched %d of %d repos." % (start, len(repo_names)))
                break
            for issue in results:
                repo_name = _repo_from_issue(issue)
                if per_repo[repo_name] >= MAX_PER_REPO:
                    continue
                per_repo[repo_name] += 1
                found.append(issue)
        return found

    def _prescore(self, issue: dict) -> float:
        updated = days_between(issue.get("updated_at"), self.now)
        score = -min(365.0 if updated is None else updated, 365.0) / 30.0
        score -= max(0, issue.get("comments", 0) - 5) * 0.5
        if len(issue.get("body") or "") >= 300:
            score += 1
        return score

    def _enrich(self, issue: dict, profile: Profile) -> Candidate:
        repo_name = _repo_from_issue(issue)
        candidate = _candidate(issue, repo_name)
        candidate.repo_health = self._health[repo_name]
        self._attach_signals(candidate, issue)
        return evaluate(candidate, profile, self.now)

    def _attach_signals(self, candidate: Candidate, issue: dict) -> None:
        candidate.signals = analyze_timeline(
            self.client.get_timeline(candidate.repo, candidate.number), candidate.repo, candidate.signals.assignees, self.now
        )
        planted = detect_injection(candidate.title + "\n" + candidate.body)
        if planted:
            author = (issue.get("user") or {}).get("login", "")
            candidate.signals.injection_hints.insert(0, Mention(author, candidate.created_at, candidate.url, planted))

    def _repo_health(self, repo_name: str, repo: Optional[dict] = None):
        if repo_name not in self._health:
            repo = repo or self.client.get_repo(repo_name)
            self._health[repo_name] = repo_health(repo, self.client.recent_closed_pulls(repo_name))
        return self._health[repo_name]

    # --- Single issue --------------------------------------------------------

    def inspect(self, ref: str, profile: Optional[Profile] = None) -> Candidate:
        repo_name, number = parse_issue_url(ref)
        issue = self.client.get_issue(repo_name, number)
        if "pull_request" in issue:
            raise ValueError("%s is a pull request, not an issue." % ref)
        candidate = _candidate(issue, repo_name)
        candidate.repo_health = self._repo_health(repo_name)
        self._attach_signals(candidate, issue)
        evaluate(candidate, profile or Profile(languages=[]), self.now)
        if issue.get("state") == "closed":
            candidate.flags.insert(0, "closed")
            candidate.verdict = "skip"
        return candidate

    def related(self, ref: str, limit: int = 5) -> Dict[str, list]:
        repo_name, number = parse_issue_url(ref)
        return find_related(self.client, repo_name, self.client.get_issue(repo_name, number), limit)

    def conventions(self, repo_name: str) -> Dict[str, object]:
        repo_name = check_repo(repo_name)
        guide = conv.fetch_contributing(self.client, repo_name)
        if guide is None:
            return {"repo": repo_name, "contributing_url": None, "rules": [], "setup_commands": [], "test_commands": [], "lint_commands": []}
        parsed = conv.parse_conventions(guide["text"])
        parsed.update({"repo": repo_name, "contributing_url": guide["url"]})
        return parsed

    def brief_facts(self, ref: str, profile: Optional[Profile] = None) -> Dict[str, object]:
        """Everything a contributor (or the model) needs to plan the first PR, gathered deterministically."""
        candidate = self.inspect(ref, profile)
        health = candidate.repo_health
        facts: Dict[str, object] = {
            "issue": candidate.to_dict(include_body=True),
            "evidence": evidence(candidate, self.now),
            "keywords": keywords(candidate.title, candidate.body),
            "related": {key: [vars(item) for item in items] for key, items in self.related(ref).items()},
            "conventions": self.conventions(candidate.repo),
            "likely_files": [],
        }
        try:
            tree = self.client.get_tree(candidate.repo, health.default_branch if health else "HEAD")
            facts["likely_files"] = conv.likely_files(tree, candidate.title, candidate.body)
        except GitHubError as exc:
            facts["likely_files_error"] = str(exc)
        return facts


def _repo_from_issue(issue: dict) -> str:
    return "/".join(issue.get("repository_url", "").rstrip("/").split("/")[-2:])


def _candidate(issue: dict, repo_name: str) -> Candidate:
    candidate = Candidate(
        repo=repo_name,
        number=issue["number"],
        title=issue.get("title", ""),
        url=issue.get("html_url", ""),
        labels=[label["name"] if isinstance(label, dict) else label for label in issue.get("labels", [])],
        created_at=issue.get("created_at", ""),
        updated_at=issue.get("updated_at", ""),
        comments=issue.get("comments", 0),
        body=issue.get("body") or "",
        locked=bool(issue.get("locked")),
    )
    candidate.signals = IssueSignals(assignees=[a["login"] for a in issue.get("assignees") or []])
    return candidate
