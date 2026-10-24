"""Understand a student from their public GitHub, then find open-source work that fits.

- analyze_profile(handle): languages, topics, recent projects and outside
  contributions -> a tech stack and an experience level.
- find_work(languages, topics, level): open, unassigned beginner-friendly issues
  and well-kept repos across GitHub, ranked by fit, with a "why it fits" list.
- issue_details(issue): the issue, its latest comments, the repo's own
  CONTRIBUTING.md and the files most likely involved, for mentoring and drafting.

Everything returned from GitHub is written by strangers. Free text (bios, issue
bodies, comments, file contents) is wrapped in <untrusted> tags by the caller.
All calls go through source.github_api (GITHUB_TOKEN or the gh CLI login).
GitHub's *secondary* rate limit punishes bursts of searches, so: few searches
per request, spaced out, cached for 30 minutes, and a 2-minute global backoff
(GitHubBusy) the moment GitHub says 403/429. Callers then fall back to event
challenges instead of failing.
"""

from __future__ import annotations

import base64
import logging
import math
import threading
import urllib.error
import re
import time
import urllib.parse
from collections import Counter
from datetime import datetime, timedelta, timezone

from .. import source
from . import config

log = logging.getLogger(__name__)
_cache: dict[str, tuple[float, object]] = {}
CACHE_S = 1800
SEARCH_SPACING_S = 2.0
BACKOFF_S = 120
_state = {"backoff_until": 0.0, "last_search": 0.0}
_search_lock = threading.Lock()
STOP = set("""a an the and or for to of in on with from by is are be this that it as at add adding fix fixes fixed
support update use using when should can not into new issue bug feature docs doc make allow error
example need want would like md py js ts""".split())
# Topics that say nothing about what a student can work on.
META_TOPICS = re.compile(r"(hac?k?toberfest|first-?contributions?|good-?first-?issues?|github|config|awesome|"
                         r"beginners?|portfolio|assignment|practice|tutorial|learning|college)([-_]?[a-z0-9]+)*")
LANGUAGE_TOPICS = re.compile(r"python|javascript|typescript|java|html|css|c|cpp|go|rust|ruby|php|kotlin|swift|dart|"
                             r"readme|website|project")


def meaningful_topic(topic: str) -> bool:
    t = topic.lower()
    return not (META_TOPICS.fullmatch(t) or LANGUAGE_TOPICS.fullmatch(t))


class GitHubBusy(RuntimeError):
    """GitHub asked us to slow down; try again in a couple of minutes."""


def _get(path: str):
    hit = _cache.get(path)
    if hit and time.time() - hit[0] < CACHE_S:
        return hit[1]
    if time.time() < _state["backoff_until"]:
        raise GitHubBusy("GitHub rate limit: backing off")
    try:
        data = source.github_api(path)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            try:
                wait = int((e.headers or {}).get("Retry-After") or BACKOFF_S)
            except (TypeError, ValueError):
                wait = BACKOFF_S
            _state["backoff_until"] = time.time() + min(max(wait, 30), 600)
            log.warning("GitHub rate limit (%s) on %s; backing off %ss", e.code, path.split("?")[0], wait)
            raise GitHubBusy(f"GitHub rate limit ({e.code})") from e
        raise
    _cache[path] = (time.time(), data)
    return data


def _search(kind: str, q: str, **params) -> dict:
    qs = urllib.parse.urlencode({"q": q, **params})
    path = f"search/{kind}?{qs}"
    if path in _cache and time.time() - _cache[path][0] < CACHE_S:
        return _cache[path][1]
    with _search_lock:  # space searches out: bursts trip GitHub's secondary rate limit
        wait = _state["last_search"] + SEARCH_SPACING_S - time.time()
        if wait > 0:
            time.sleep(wait)
        _state["last_search"] = time.time()
        return _get(path)


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")


def _age_days(iso: str | None) -> int:
    if not iso:
        return 9999
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days


# --- profile ----------------------------------------------------------------


def analyze_profile(handle: str) -> dict:
    """Public GitHub signals -> stack + experience level. Raises on unknown users."""
    user = _get(f"users/{handle}")
    repos = _get(f"users/{handle}/repos?per_page=100&sort=pushed") or []
    own = [r for r in repos if not r.get("fork")]
    langs = Counter(r["language"] for r in own[:40] if r.get("language"))
    topics = Counter(t for r in own[:40] for t in r.get("topics", []) if meaningful_topic(t))
    prs = _search("issues", f"type:pr author:{handle} -user:{handle}", per_page=100)  # one search, not two
    opened = prs.get("total_count", 0)
    merged = sum(1 for it in prs.get("items", []) if (it.get("pull_request") or {}).get("merged_at"))
    years = round(_age_days(user.get("created_at")) / 365, 1)
    stars = sum(r.get("stargazers_count", 0) for r in own)

    if merged >= 10 or (len(own) >= 25 and stars >= 50):
        level = "advanced"
    elif merged >= 1 or len(own) >= 5:
        level = "intermediate"
    else:
        level = "beginner"
    signals = [f"{len(own)} own public repos", f"{merged} merged PRs to other people's projects",
               f"{opened} PRs opened to other projects", f"account {years} years old", f"{stars} stars on own repos"]
    return {
        "handle": user.get("login", handle),
        "bio": (user.get("bio") or "")[:200],
        "top_languages": [l for l, _ in langs.most_common(5)],
        "topics": [t for t, n in topics.most_common(10) if n >= 2] or [t for t, _ in topics.most_common(3)],
        "recent_projects": [{"name": r["name"], "language": r.get("language"), "topics": r.get("topics", [])[:5],
                             "description": (r.get("description") or "")[:120]} for r in own[:5]],
        "merged_external_prs": merged,
        "external_prs": opened,
        "level": level,
        "signals": signals,
    }


# --- discovery --------------------------------------------------------------


def _stem(word: str) -> str:
    """Tiny plural folding so "dependency" matches "dependencies.py"."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _keywords(text: str, limit: int = 10) -> list[str]:
    words = [_stem(w) for w in re.findall(r"[a-z][a-z0-9]{2,}", text.lower())]
    return [w for w, _ in Counter(w for w in words if w not in STOP).most_common(limit)]


def find_work(languages: list[str], topics: list[str], level: str, student: str = "",
              limit: int = 6) -> dict:
    """Rank open, unassigned, beginner-friendly issues and active repos for this student."""
    langs = [l for l in languages if l][:2] or ["Python"]
    topic = next((t for t in topics if t and re.fullmatch(r"[\w.-]+", t)), "")
    label = '"good first issue"' if level == "beginner" else '"good first issue","help wanted"'  # comma = OR
    since = _days_ago(90)
    found: dict[str, dict] = {}
    # At most 2 issue searches: main language with the student's topic, then the second language.
    plan = [(langs[0], topic)] + ([(langs[1], "")] if len(langs) > 1 else [(langs[0], "")] if topic else [])
    for lang, extra in plan:
        q = (f"label:{label} state:open type:issue no:assignee archived:false language:{lang} "
             f"comments:<8 updated:>{since} {extra}").strip()
        for it in _search("issues", q, per_page=10, sort="updated").get("items", []):
            repo = "/".join(it["repository_url"].split("/")[-2:])
            key = f"{repo}#{it['number']}"
            if key not in found and "pull_request" not in it:
                found[key] = {"id": key, "repo": repo, "title": it["title"][:120], "url": it["html_url"],
                              "labels": [l["name"] for l in it.get("labels", [])][:6],
                              "comments": it.get("comments", 0), "updated_days": _age_days(it.get("updated_at")),
                              "body": (it.get("body") or "")[:500], "language": lang}

    # Repo quality filter: real, active, community projects only.
    meta: dict[str, dict] = {}
    for repo in list(dict.fromkeys(i["repo"] for i in found.values()))[:10]:
        try:
            meta[repo] = _get(f"repos/{repo}")
        except GitHubBusy:
            break
        except Exception:
            continue
    issues = []
    for i in found.values():
        m = meta.get(i["repo"])
        if not m or m.get("archived") or m.get("fork") or m.get("stargazers_count", 0) < config.MIN_STARS:
            continue
        if student and m.get("owner", {}).get("login", "").lower() == student.lower():
            continue
        why, score = [], 0.0
        if (m.get("language") or "").lower() in [l.lower() for l in langs]:
            why.append(f"written in {m['language']}, which you know")
            score += 3
        overlap = [t for t in m.get("topics", []) if t in topics]
        if overlap:
            why.append("about " + ", ".join(overlap[:3]) + ", like your projects")
            score += 2 * len(overlap[:3])
        if any("good first" in l.lower() for l in i["labels"]):
            why.append("maintainers marked it beginner-friendly")
            score += 2 if level == "beginner" else 1
        if i["comments"] <= 2:
            why.append("nobody is working on it yet")
            score += 1
        score += min(3.0, math.log10(max(m.get("stargazers_count", 1), 1))) - i["updated_days"] / 60
        issues.append({**i, "stars": m.get("stargazers_count", 0), "license": (m.get("license") or {}).get("spdx_id"),
                       "repo_description": (m.get("description") or "")[:140], "why": why, "score": round(score, 2),
                       "points_eligible": i["repo"] in config.REPOS})
    issues.sort(key=lambda x: -x["score"])

    # Projects worth following: the best-fitting repos we already looked at (no extra search).
    repos, seen = [], set()
    for i in issues:
        if i["repo"] in seen or len(repos) == 3:
            continue
        seen.add(i["repo"])
        repos.append({"repo": i["repo"], "stars": i["stars"], "url": f"https://github.com/{i['repo']}",
                      "description": i["repo_description"],
                      "good_first_issues": f"https://github.com/{i['repo']}/issues?q=is%3Aopen+label%3A%22good+first+issue%22"})
    return {"issues": issues[:limit], "repos_to_explore": repos}


# --- the student's own PRs ---------------------------------------------------


def my_prs(handle: str) -> tuple[list[dict], list[dict]]:
    """PRs authored by `handle` (one search): open ones, and ones merged in the last 90 days."""
    items = _search("issues", f"type:pr author:{handle} updated:>{_days_ago(90)}", sort="updated",
                    per_page=30).get("items", [])
    open_ = [i for i in items if i.get("state") == "open"][:5]
    merged = [i for i in items if (i.get("pull_request") or {}).get("merged_at")][:5]
    return open_, merged


# --- one issue in depth -----------------------------------------------------


def issue_details(repo: str, number: int) -> dict:
    """Issue + recent comments + repo rules + the files most likely involved."""
    issue = _get(f"repos/{repo}/issues/{number}")
    meta = _get(f"repos/{repo}")
    comments = _get(f"repos/{repo}/issues/{number}/comments?per_page=30") or []
    branch = meta.get("default_branch", "main")
    paths: list[str] = []
    try:
        tree = _get(f"repos/{repo}/git/trees/{urllib.parse.quote(branch)}?recursive=1")
        paths = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]
    except Exception:
        pass
    text = f"{issue.get('title', '')}\n{issue.get('body') or ''}"
    mentioned = [p for p in paths if p in text or (len(p.split("/")[-1]) > 5 and p.split("/")[-1] in text)]
    kws = _keywords(text)
    scored = []
    for p in paths:
        if p in mentioned or re.search(r"(^|/)(node_modules|dist|build|vendor|\.git)/", p):
            continue
        parts = [_stem(x) for x in re.split(r"[/_.-]", p.lower()) if x]
        hits = sum(1 for k in kws if k in parts or (len(k) > 4 and any(k in x for x in parts)))
        if hits:
            scored.append((hits, -len(p), p))
    candidates = mentioned[:5] + [p for _, _, p in sorted(scored, reverse=True)[: 8 - len(mentioned[:5])]]
    contributing = ""
    for name in ("CONTRIBUTING.md", ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md"):
        if name in paths:
            contributing = read_file(repo, name, branch, 1500)
            break
    return {
        "repo": repo, "number": number, "url": issue.get("html_url"), "title": issue.get("title"),
        "state": issue.get("state"), "assignees": [a["login"] for a in issue.get("assignees", [])],
        "labels": [l["name"] for l in issue.get("labels", [])], "body": (issue.get("body") or "")[:3000],
        "recent_comments": [{"author": c["user"]["login"], "text": (c.get("body") or "")[:500]} for c in comments[-3:]],
        "repo_language": meta.get("language"), "default_branch": branch, "stars": meta.get("stargazers_count"),
        "license": (meta.get("license") or {}).get("spdx_id"), "candidate_files": candidates,
        "contributing_excerpt": contributing, "has_tests": any(re.search(r"(^|/)tests?/", p) for p in paths),
    }


def read_file(repo: str, path: str, ref: str | None = None, limit: int = 6000) -> str:
    q = f"?ref={urllib.parse.quote(ref)}" if ref else ""
    data = _get(f"repos/{repo}/contents/{urllib.parse.quote(path)}{q}")
    if isinstance(data, list) or data.get("encoding") != "base64":
        return ""
    raw = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
    return raw[:limit] + ("\n… (truncated)" if len(raw) > limit else "")
