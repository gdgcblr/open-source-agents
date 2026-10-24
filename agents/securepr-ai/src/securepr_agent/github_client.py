"""GitHub REST API client for fetching PR metadata and posting review comments."""
import os
import re
import json
from typing import Dict, List, Optional
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_REQUESTS = False
from securepr_agent.models import PullRequestFile, PullRequestMetadata


class GitHubClient:
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.base_url = "https://api.github.com"

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SecurePR-AI-Review-Agent/0.1.0",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        return headers

    @staticmethod
    def parse_pr_url(pr_url: str) -> Optional[Dict[str, str]]:
        """Extracts owner, repo, and pull_number from a GitHub PR URL."""
        match = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
        if match:
            return {
                "owner": match.group(1),
                "repo": match.group(2),
                "pull_number": match.group(3),
            }
        return None

    def _get(self, url: str) -> dict:
        if HAS_REQUESTS:
            res = requests.get(url, headers=self._headers(), timeout=15)
            if res.status_code == 404:
                raise RuntimeError(f"Resource not found (404): {url}")
            res.raise_for_status()
            return res.json()
        else:
            req = urllib.request.Request(url, headers=self._headers())
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                raise RuntimeError(f"HTTP {e.code}: {e.reason} for {url}")

    def _post(self, url: str, data: dict) -> bool:
        if HAS_REQUESTS:
            res = requests.post(url, headers=self._headers(), json=data, timeout=15)
            return res.status_code in [200, 201]
        else:
            body = json.dumps(data).encode("utf-8")
            headers = self._headers()
            headers["Content-Type"] = "application/json"
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return resp.status in [200, 201]
            except Exception:
                return False

    def fetch_pull_request(self, pr_url: str) -> PullRequestMetadata:
        """Fetches PR metadata and list of changed files with diff patches."""
        parsed = self.parse_pr_url(pr_url)
        if not parsed:
            raise ValueError(f"Invalid GitHub PR URL format: {pr_url}")

        owner = parsed["owner"]
        repo = parsed["repo"]
        pr_number = int(parsed["pull_number"])

        # Fetch PR details
        pr_endpoint = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}"
        pr_data = self._get(pr_endpoint)

        # Fetch changed files
        files_endpoint = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/files"
        files_data = self._get(files_endpoint)

        files: List[PullRequestFile] = []
        for f in files_data:
            files.append(
                PullRequestFile(
                    filename=f.get("filename", ""),
                    status=f.get("status", "modified"),
                    additions=f.get("additions", 0),
                    deletions=f.get("deletions", 0),
                    changes=f.get("changes", 0),
                    patch=f.get("patch", ""),
                    raw_content=f.get("patch", ""),
                )
            )

        return PullRequestMetadata(
            repo_full_name=f"{owner}/{repo}",
            pr_number=pr_number,
            title=pr_data.get("title", f"PR #{pr_number}"),
            author=pr_data.get("user", {}).get("login", "unknown"),
            base_ref=pr_data.get("base", {}).get("ref", "main"),
            head_ref=pr_data.get("head", {}).get("ref", "head"),
            html_url=pr_data.get("html_url", pr_url),
            files=files,
        )

    def post_comment(self, pr_url: str, markdown_body: str) -> bool:
        """Posts a review comment to the GitHub pull request."""
        parsed = self.parse_pr_url(pr_url)
        if not parsed:
            return False

        if not self.token:
            print("[SecurePR Agent] Warning: GITHUB_TOKEN not set; skipping live GitHub comment post.")
            return False

        owner = parsed["owner"]
        repo = parsed["repo"]
        pr_number = parsed["pull_number"]

        endpoint = f"{self.base_url}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        return self._post(endpoint, {"body": markdown_body})
