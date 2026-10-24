"""
RepoLens — URL Validator and Input Sanitizer

Only public GitHub repository URLs are accepted.
All validation is done before any external network call.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Allowed GitHub hostname — only github.com, no redirects.
_GITHUB_HOSTNAME = "github.com"

# Repo path pattern: /owner/repo (no extra path segments for MVP)
_REPO_PATH_RE = re.compile(
    r"^/([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+?)(?:\.git)?/?$"
)

# Characters that could be used for shell injection (defense-in-depth;
# the actual subprocess calls use arg arrays, not shell=True).
_DANGEROUS_CHARS_RE = re.compile(r"[;&|`$<>()\[\]{}\\'\"]")


class ValidationError(ValueError):
    """Raised when a repository URL fails validation."""
    pass


def validate_github_url(url: str) -> tuple[str, str]:
    """
    Validate and normalize a public GitHub repository URL.

    Returns:
        (normalized_url, repo_name) where repo_name is 'owner/repo'.

    Raises:
        ValidationError on any invalid input.
    """
    if not url or not isinstance(url, str):
        raise ValidationError("Repository URL must be a non-empty string.")

    url = url.strip()

    if len(url) > 2048:
        raise ValidationError("Repository URL exceeds maximum length (2048 chars).")

    if _DANGEROUS_CHARS_RE.search(url):
        raise ValidationError("Repository URL contains disallowed characters.")

    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValidationError(f"Could not parse URL: {exc}") from exc

    if parsed.scheme not in ("https", "http"):
        raise ValidationError("Repository URL must use https://.")

    if parsed.scheme == "http":
        raise ValidationError("Repository URL must use https:// (not http://).")

    hostname = parsed.hostname or ""
    if hostname != _GITHUB_HOSTNAME:
        raise ValidationError(
            f"Only public GitHub repositories are supported (github.com). "
            f"Got: {hostname!r}"
        )

    if parsed.port is not None:
        raise ValidationError("Repository URL must not specify a port.")

    m = _REPO_PATH_RE.match(parsed.path)
    if not m:
        raise ValidationError(
            "URL path must be /owner/repo (e.g. https://github.com/owner/repo)."
        )

    owner, repo = m.group(1), m.group(2)
    repo_name = f"{owner}/{repo}"
    normalized = f"https://github.com/{repo_name}"
    return normalized, repo_name


def build_clone_args(normalized_url: str, dest_dir: str) -> list[str]:
    """
    Return a safe subprocess argument list for shallow cloning.
    The URL and dest_dir are validated before this function is called.
    shell=False MUST be used when invoking this list.
    """
    return [
        "git",
        "clone",
        "--depth", "1",
        "--single-branch",
        "--no-tags",
        "--",            # explicit end of options: prevents git treating URL as flag
        normalized_url,
        dest_dir,
    ]
