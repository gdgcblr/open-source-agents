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
from .plan import next_step
from .pointers import code_pointers
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
        result = ScoutResult(profile, good[:limit], skipped, len(repos), self.client.requests_made, notes)
        result.legwork = _legwork(evaluated)
        return result

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
        notes: List[str] = []
        facts: Dict[str, object] = {
            "issue": candidate.to_dict(include_body=True),
            "evidence": evidence(candidate, self.now),
            "keywords": keywords(candidate.title, candidate.body),
            "related": {"open_issues": [], "closed_issues": [], "merged_prs": []},
            "conventions": {"repo": candidate.repo, "contributing_url": None, "rules": [],
                            "setup_commands": [], "test_commands": [], "lint_commands": []},
            "likely_files": [],
            "code_pointers": {"identifiers": [], "pointers": [], "searched_files": []},
            "notes": notes,
        }
        # The availability check above is essential; the extras below degrade gracefully.
        try:
            facts["related"] = {key: [vars(item) for item in items] for key, items in self.related(ref).items()}
        except GitHubError as exc:
            notes.append("Related issues unavailable: %s" % exc)
        try:
            facts["conventions"] = self.conventions(candidate.repo)
        except GitHubError as exc:
            notes.append("Contributing guide unavailable: %s" % exc)
        branch = health.default_branch if health else "HEAD"
        tree_paths: List[str] = []
        try:
            tree = self.client.get_tree(candidate.repo, branch)
            tree_paths = [entry["path"] for entry in tree if entry.get("type") == "blob"]
            facts["likely_files"] = conv.likely_files(tree, candidate.title, candidate.body)
        except GitHubError as exc:
            notes.append("File suggestions unavailable: %s" % exc)
        try:
            facts["code_pointers"] = code_pointers(
                self.client, candidate.repo, branch, candidate.title, candidate.body,
                [entry["path"] for entry in facts["likely_files"][:3]], tree_paths,
            )
        except GitHubError as exc:
            notes.append("Code pointers unavailable: %s" % exc)

        pointers = facts["code_pointers"]["pointers"]
        # Files that actually contain the issue's identifiers beat files whose names merely match.
        pointer_files: List[str] = []
        for pointer in pointers:
            if pointer["path"] not in pointer_files:
                pointer_files.append(pointer["path"])
        if pointer_files:
            ranked = [{"path": path, "why": "contains " + ", ".join(sorted({"`%s`" % p["term"] for p in pointers if p["path"] == path}))}
                      for path in pointer_files]
            ranked += [entry for entry in facts["likely_files"] if entry["path"] not in pointer_files]
            facts["likely_files"] = ranked[:8]
        first_file = facts["likely_files"][0]["path"] if facts["likely_files"] else None
        facts["next_step"] = next_step(candidate, facts["conventions"], first_file, self.now)
        return facts


def _legwork(evaluated: List[Candidate]) -> Dict[str, int]:
    """The manual checking this run did on the contributor's behalf."""
    repos = {c.repo: c.repo_health for c in evaluated if c.repo_health is not None}
    return {
        "issues_checked": len(evaluated),
        "comments_read": sum(c.signals.comments_read for c in evaluated if c.signals),
        "cross_references_followed": sum(c.signals.cross_references for c in evaluated if c.signals),
        "repos_merge_history_checked": len(repos),
        "closed_prs_reviewed": sum(h.closed_sample for h in repos.values()),
    }


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
