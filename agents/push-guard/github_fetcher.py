import re
import httpx
from typing import Optional
from pydantic import BaseModel


class CommitInfo(BaseModel):
    sha: str
    short_sha: str
    message: str
    author: str
    date: str
    files_changed: int
    additions: int
    deletions: int
    url: str


class FetchedDiff(BaseModel):
    owner: str
    repo: str
    branch: str
    commit: CommitInfo
    diff: str


def _parse_repo_url(url: str) -> tuple[str, str]:
    url = url.strip().rstrip("/")
    # Full URL: https://github.com/owner/repo
    match = re.search(r"github\.com[:/]([^/]+)/([^/\.]+)", url)
    if match:
        return match.group(1), match.group(2).removesuffix(".git")
    # Shorthand: owner/repo
    match = re.fullmatch(r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", url)
    if match:
        return match.group(1), match.group(2).removesuffix(".git")
    raise ValueError(f"Could not parse GitHub owner/repo from: {url}")


def _build_diff_from_files(files: list[dict]) -> str:
    """Reconstruct a unified diff from GitHub commit file patches."""
    parts = []
    for f in files:
        filename = f.get("filename", "")
        patch = f.get("patch", "")
        if not patch:
            continue
        status = f.get("status", "modified")
        if status == "added":
            parts.append(f"diff --git a/dev/null b/{filename}")
            parts.append(f"--- /dev/null")
            parts.append(f"+++ b/{filename}")
        elif status == "removed":
            parts.append(f"diff --git a/{filename} b/dev/null")
            parts.append(f"--- a/{filename}")
            parts.append(f"+++ /dev/null")
        else:
            parts.append(f"diff --git a/{filename} b/{filename}")
            parts.append(f"--- a/{filename}")
            parts.append(f"+++ b/{filename}")
        parts.append(patch)
    return "\n".join(parts)


def fetch_latest_commit_diff(
    repo_url: str,
    branch: str = "main",
    github_token: Optional[str] = None,
    num_commits: int = 1,
) -> FetchedDiff:
    owner, repo = _parse_repo_url(repo_url)
    num_commits = max(1, min(num_commits, 5))

    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    with httpx.Client(timeout=30) as client:
        commits_url = f"https://api.github.com/repos/{owner}/{repo}/commits"
        r = client.get(commits_url, headers=headers, params={"sha": branch, "per_page": num_commits})
        if r.status_code == 404:
            raise ValueError(f"Repository or branch '{branch}' not found. Check the URL and try 'master' instead of 'main' (or vice versa).")
        if r.status_code == 403:
            raise ValueError("GitHub API rate limit hit. Wait a minute and try again, or add a GITHUB_TOKEN to your .env.")
        r.raise_for_status()
        commits = r.json()
        if not commits:
            raise ValueError(f"No commits found on branch '{branch}'")

        # Use the latest commit as the reference for metadata
        latest = commits[0]
        latest_sha = latest["sha"]
        latest_commit_data = latest["commit"]

        # Fetch full detail (with patches) for each commit and combine diffs
        combined_diff_parts = []
        total_additions = 0
        total_deletions = 0
        total_files: set[str] = set()

        for commit_summary in commits:
            sha = commit_summary["sha"]
            commit_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}"
            r2 = client.get(commit_url, headers=headers)
            if r2.status_code != 200:
                continue
            detail = r2.json()
            files = detail.get("files", [])
            patch = _build_diff_from_files(files)
            if patch.strip():
                combined_diff_parts.append(f"# commit {sha[:7]}: {commit_summary['commit']['message'].splitlines()[0]}\n{patch}")
            stats = detail.get("stats", {})
            total_additions += stats.get("additions", 0)
            total_deletions += stats.get("deletions", 0)
            total_files.update(f.get("filename", "") for f in files)

    combined_diff = "\n\n".join(combined_diff_parts)

    label = f"last {num_commits} commit{'s' if num_commits > 1 else ''}"
    commit_info = CommitInfo(
        sha=latest_sha,
        short_sha=latest_sha[:7],
        message=f"[{label}] {latest_commit_data.get('message', '').splitlines()[0]}",
        author=latest_commit_data.get("author", {}).get("name", "unknown"),
        date=latest_commit_data.get("author", {}).get("date", ""),
        files_changed=len(total_files),
        additions=total_additions,
        deletions=total_deletions,
        url=f"https://github.com/{owner}/{repo}/commit/{latest_sha}",
    )

    return FetchedDiff(
        owner=owner,
        repo=repo,
        branch=branch,
        commit=commit_info,
        diff=combined_diff,
    )
