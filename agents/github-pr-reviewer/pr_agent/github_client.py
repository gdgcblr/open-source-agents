import os
import re
import sys
from typing import Optional, Tuple
import requests


def parse_pr_target(target: str) -> Optional[Tuple[str, str, int]]:
    """Extract (owner, repo, pr_number) from URL or slug format."""
    # Match URL: https://github.com/owner/repo/pull/123
    url_match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", target)
    if url_match:
        return url_match.group(1), url_match.group(2), int(url_match.group(3))

    # Match slug: owner/repo#123
    slug_match = re.match(r"([^/]+)/([^#]+)#(\d+)", target)
    if slug_match:
        return slug_match.group(1), slug_match.group(2), int(slug_match.group(3))

    return None


def fetch_pr_diff(target: str, token: Optional[str] = None) -> Tuple[str, str]:
    """
    Fetch unified diff text for a GitHub PR.
    Returns (diff_text, display_title).
    """
    parsed = parse_pr_target(target)
    if not parsed:
        raise ValueError(f"Invalid PR target: '{target}'. Expected 'https://github.com/owner/repo/pull/123' or 'owner/repo#123'")

    owner, repo, pr_number = parsed
    display_title = f"{owner}/{repo}#{pr_number}"

    # Try GitHub API first if token or standard headers
    headers = {
        "User-Agent": "open-source-ai-pr-reviewer/0.1.0",
        "Accept": "application/vnd.github.v3.diff",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    response = requests.get(api_url, headers=headers, timeout=20)

    if response.status_code == 200:
        return response.text, display_title

    # Fallback to direct raw diff URL
    diff_url = f"https://github.com/{owner}/{repo}/pull/{pr_number}.diff"
    raw_response = requests.get(diff_url, headers={"User-Agent": "open-source-ai-pr-reviewer"}, timeout=20)
    if raw_response.status_code == 200:
        return raw_response.text, display_title

    raise RuntimeError(
        f"Failed to fetch diff for {display_title}. "
        f"API status: {response.status_code}, Web status: {raw_response.status_code}. "
        "Check repository permissions or provide GITHUB_TOKEN."
    )


def load_diff_from_file(file_path: str) -> Tuple[str, str]:
    """Load unified diff from local file."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Diff file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read(), os.path.basename(file_path)


def load_diff_from_stdin() -> Tuple[str, str]:
    """Load diff from standard input."""
    content = sys.stdin.read()
    if not content.strip():
        raise ValueError("No diff content received from stdin.")
    return content, "Standard Input (stdin)"
