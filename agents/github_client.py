"""Minimal GitHub REST client: fetch a PR's diff and post the review as a comment."""
from __future__ import annotations

import os
import re

import requests

API = "https://api.github.com"
PR_REF = re.compile(r"^(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)#(?P<num>\d+)$")


class GitHubError(RuntimeError):
    pass


def parse_pr_ref(ref: str) -> tuple[str, str, int]:
    m = PR_REF.match(ref.strip())
    if not m:
        raise GitHubError("PR reference must look like owner/repo#123")
    return m["owner"], m["repo"], int(m["num"])


def _headers(accept: str) -> dict:
    h = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def fetch_pr_diff(ref: str) -> str:
    owner, repo, num = parse_pr_ref(ref)
    r = requests.get(f"{API}/repos/{owner}/{repo}/pulls/{num}",
                     headers=_headers("application/vnd.github.v3.diff"), timeout=30)
    if r.status_code != 200:
        raise GitHubError(f"GitHub returned HTTP {r.status_code}")
    if len(r.content) > 1_000_000:
        raise GitHubError("PR diff exceeds 1 MB")
    return r.text


def post_comment(ref: str, body: str) -> str:
    owner, repo, num = parse_pr_ref(ref)
    if os.getenv("ALLOW_GITHUB_POST", "").lower() != "true":
        raise GitHubError("Set ALLOW_GITHUB_POST=true to authorize posting")
    if not os.environ.get("GITHUB_TOKEN"):
        raise GitHubError("GITHUB_TOKEN is required to post a comment")
    if len(body) > 60000:
        raise GitHubError("Review comment exceeds safe length")
    if len(body) > 60000:
        raise GitHubError("Comment too long")
    r = requests.post(f"{API}/repos/{owner}/{repo}/issues/{num}/comments",
                      headers=_headers("application/vnd.github+json"),
                      json={"body": body}, timeout=30)
    if r.status_code != 201:
        raise GitHubError(f"GitHub returned HTTP {r.status_code}")
    return r.json().get("html_url", "")
