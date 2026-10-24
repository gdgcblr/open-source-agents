import os
import re
import sys
from typing import Optional, Tuple
import requests

from .exceptions import InvalidTargetError, GitHubFetchError, DiffReadError


def parse_pr_target(target: str) -> Optional[Tuple[str, str, int]]:
    """Extract (owner, repo, pr_number) from URL or slug format."""
    if not target or not isinstance(target, str):
        return None

    target = target.strip()

    # Match URL: https://github.com/owner/repo/pull/123
    url_match = re.match(r"^https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)(?:/.*)?$", target)
    if url_match:
        return url_match.group(1), url_match.group(2), int(url_match.group(3))

    # Match slug: owner/repo#123
    slug_match = re.match(r"^([^/]+)/([^#]+)#(\d+)$", target)
    if slug_match:
        return slug_match.group(1), slug_match.group(2), int(slug_match.group(3))

    return None


def fetch_pr_diff(target: str, token: Optional[str] = None) -> Tuple[str, str]:
    """
    Fetch unified diff text for a GitHub PR with comprehensive exception diagnostics.
    Returns (diff_text, display_title).
    """
    parsed = parse_pr_target(target)
    if not parsed:
        raise InvalidTargetError(
            f"Invalid PR target format: '{target}'.",
            tip="Provide a full GitHub URL (e.g. 'https://github.com/owner/repo/pull/123') or slug ('owner/repo#123')."
        )

    owner, repo, pr_number = parsed
    display_title = f"{owner}/{repo}#{pr_number}"

    headers = {
        "User-Agent": "open-source-ai-pr-reviewer/0.1.0",
        "Accept": "application/vnd.github.v3.diff",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"

    try:
        response = requests.get(api_url, headers=headers, timeout=20)
    except requests.exceptions.Timeout:
        raise GitHubFetchError(
            f"Connection timed out while fetching {display_title} from GitHub API.",
            tip="Check your internet connection or GitHub status at https://www.githubstatus.com."
        )
    except requests.exceptions.ConnectionError:
        raise GitHubFetchError(
            f"Failed to connect to GitHub API for {display_title}.",
            tip="Ensure your network allows outbound HTTPS traffic to api.github.com."
        )
    except requests.exceptions.RequestException as e:
        raise GitHubFetchError(
            f"Network request error fetching {display_title}: {e}",
            tip="Verify URL and try again."
        )

    if response.status_code == 200:
        if not response.text.strip():
            raise GitHubFetchError(
                f"PR {display_title} contains an empty diff (zero additions/deletions).",
                tip="Ensure the pull request has commits touching tracked files."
            )
        return response.text, display_title

    # Diagnostic handling for non-200 responses
    if response.status_code == 404:
        # Fallback to direct raw web diff endpoint before declaring 404
        diff_url = f"https://github.com/{owner}/{repo}/pull/{pr_number}.diff"
        try:
            raw_resp = requests.get(diff_url, headers={"User-Agent": "open-source-ai-pr-reviewer"}, timeout=20)
            if raw_resp.status_code == 200 and raw_resp.text.strip():
                return raw_resp.text, display_title
        except requests.exceptions.RequestException:
            pass

        raise GitHubFetchError(
            f"Pull Request {display_title} was not found (HTTP 404).",
            tip="Check repository spelling and PR number. If the repo is private, provide --token <GITHUB_TOKEN>."
        )
    elif response.status_code == 403:
        raise GitHubFetchError(
            f"GitHub API access forbidden for {display_title} (HTTP 403: Rate Limit Exceeded or Scope Denied).",
            tip="Set GITHUB_TOKEN in your .env or pass --token to bypass unauthenticated rate limits (60 req/hr)."
        )
    elif response.status_code == 401:
        raise GitHubFetchError(
            f"GitHub authentication failed (HTTP 401: Bad Credentials).",
            tip="Verify that your GITHUB_TOKEN is active and has not expired."
        )
    else:
        raise GitHubFetchError(
            f"Unexpected GitHub API response {response.status_code} for {display_title}: {response.text[:200]}",
            tip="Try again later or use --diff <local_patch_file>."
        )


def load_diff_from_file(file_path: str) -> Tuple[str, str]:
    """Load unified diff from local file with error diagnostics."""
    if not file_path:
        raise DiffReadError("No file path specified for diff.", tip="Provide a valid path via --diff <path>.")

    if not os.path.exists(file_path):
        raise DiffReadError(
            f"Diff file not found: '{file_path}'.",
            tip=f"Check the file path. Current working directory is: {os.getcwd()}."
        )

    if os.path.isdir(file_path):
        raise DiffReadError(
            f"Target path '{file_path}' is a directory, not a diff file.",
            tip="Point directly to a .patch or .diff file."
        )

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except PermissionError:
        raise DiffReadError(
            f"Permission denied reading '{file_path}'.",
            tip="Ensure read permissions are granted: chmod +r <file>."
        )
    except UnicodeDecodeError:
        raise DiffReadError(
            f"Failed to decode '{file_path}' as UTF-8 text.",
            tip="Ensure the patch file is plain text, not a binary git archive."
        )
    except Exception as e:
        raise DiffReadError(f"Unexpected error reading '{file_path}': {e}")

    if not content.strip():
        raise DiffReadError(
            f"Diff file '{file_path}' is empty.",
            tip="Ensure the patch file contains valid git diff text."
        )

    return content, os.path.basename(file_path)


def load_diff_from_stdin() -> Tuple[str, str]:
    """Load diff from standard input with error handling."""
    if sys.stdin.isatty():
        raise DiffReadError(
            "No diff content piped into standard input.",
            tip="Use a pipe: git diff | python main.py --stdin, or use --sample for a demo."
        )

    try:
        content = sys.stdin.read()
    except Exception as e:
        raise DiffReadError(f"Failed to read from stdin: {e}")

    if not content.strip():
        raise DiffReadError(
            "Standard input diff was empty.",
            tip="Ensure your git diff command produces output: git diff main...HEAD."
        )

    return content, "Standard Input (stdin)"
