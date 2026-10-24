
import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT = 15


def parse_github_url(url: str) -> tuple[str, str]:
    """Extract the owner and repository name from a GitHub URL."""
    match = re.match(
        r"https?://github\.com/([^/]+)/([^/?#]+)",
        url.strip().rstrip("/"),
    )

    if not match:
        raise ValueError(
            "Please provide a valid GitHub repository URL."
        )

    owner, repo = match.groups()
    repo = repo.removesuffix(".git")

    if not owner or not repo:
        raise ValueError("GitHub owner or repository name is missing.")

    return owner, repo


def get_repository_info(url: str) -> dict:
    """Fetch public repository metadata and README from GitHub."""
    try:
        owner, repo = parse_github_url(url)

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        response = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}",
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code == 403:
            remaining = response.headers.get("X-RateLimit-Remaining")
            reset = response.headers.get("X-RateLimit-Reset")
            return {
                "error": "GitHub API rate limit or access restriction.",
                "remaining_requests": remaining,
                "rate_limit_reset_unix": reset,
                "url": url,
            }

        if response.status_code == 404:
            return {
                "error": "Repository not found or not publicly accessible.",
                "url": url,
            }

        response.raise_for_status()
        data = response.json()

        readme_response = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/readme",
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

        readme = ""
        if readme_response.status_code == 200:
            readme_data = readme_response.json()
            import base64

            readme = base64.b64decode(
                readme_data.get("content", "")
            ).decode("utf-8", errors="replace")
        elif readme_response.status_code == 403:
            readme = "README unavailable because of GitHub API rate limits."
        elif readme_response.status_code == 404:
            readme = "No README was found."

        return {
            "name": data.get("full_name"),
            "description": data.get("description"),
            "language": data.get("language"),
            "stars": data.get("stargazers_count"),
            "url": data.get("html_url"),
            "default_branch": data.get("default_branch"),
            "readme": readme,
        }

    except (ValueError, requests.RequestException) as exc:
        return {"error": str(exc), "url": url}
