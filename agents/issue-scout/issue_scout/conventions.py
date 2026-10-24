"""Pull the things newcomers usually miss out of a repo's CONTRIBUTING guide and file tree."""

from __future__ import annotations

import base64
import math
import re
from typing import Dict, List, Optional

from .github import GitHubError
from .related import tokens

_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_COMMAND_START = re.compile(
    r"^(\$ )?(pip|pip3|uv|poetry|pdm|hatch|python|python3|npm|npx|pnpm|yarn|bun|make|cargo|go|pytest|tox|nox|"
    r"pre-commit|ruff|black|flake8|mypy|eslint|prettier|\./gradlew|gradle|mvn|docker|bundle|rake|dotnet|just)\b"
)
_PATH_RE = re.compile(r"(?<![\w/])([\w.-]+/[\w./-]+\.[A-Za-z0-9]{1,6}|[\w-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|kt|rb|md|yml|yaml|toml|json|c|cc|cpp|h))\b")
_SKIP_DIRS = ("node_modules/", "vendor/", "third_party/", "dist/", "build/", ".git/")
_INLINE_COMMENT_RE = re.compile(r"\s{2,}#.*$")
COMMON_WORD_SHARE = 0.25  # ignore issue words that appear in more than this share of paths

RULES = {
    "cla": (r"\bCLA\b|contributor license agreement", "Sign the CLA before your PR can be merged."),
    "dco": (r"\bDCO\b|signed-off-by|git commit -s\b|--signoff|sign[- ]off", "Sign off every commit (git commit -s)."),
    "conventional_commits": (
        r"conventional commits?|commit messages? (should|must) (start|follow)|\bfeat(\(|:)",
        "Use Conventional Commit messages (feat:, fix:, docs: ...).",
    ),
    "changelog": (r"changelog|news fragment|towncrier|changeset", "Add a changelog / news entry with your PR."),
    "discuss_first": (
        r"(open|file|create) an issue (first|before)|discuss (it |this |changes )?(first|before)",
        "Large changes should be discussed in an issue before a PR.",
    ),
    "tests_required": (r"(add|include|write) (unit )?tests|tests? (are|is) required", "PRs are expected to include tests."),
}


def fetch_contributing(client, repo: str) -> Optional[Dict[str, str]]:
    """Return {"path", "url", "text"} for the repo's contributing guide, or None."""
    try:
        profile = client.get_community_profile(repo)
    except GitHubError:
        return None
    entry = ((profile or {}).get("files") or {}).get("contributing")
    if not entry or not entry.get("url"):
        return None
    try:
        data = client.get(entry["url"])
    except GitHubError:
        return None
    if data.get("encoding") != "base64":
        return None
    text = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
    return {"path": data.get("path", "CONTRIBUTING.md"), "url": entry.get("html_url", ""), "text": text}


def parse_conventions(text: str) -> Dict[str, object]:
    found_rules = []
    for key, (pattern, advice) in RULES.items():
        if re.search(pattern, text or "", re.IGNORECASE):
            found_rules.append({"rule": key, "advice": advice})

    setup, test, lint = [], [], []
    for block in _FENCE_RE.findall(text or ""):
        for line in block.splitlines():
            command = line.strip()
            if not _COMMAND_START.match(command):
                continue
            command = command[2:] if command.startswith("$ ") else command
            command = _INLINE_COMMENT_RE.sub("", command)
            lowered = command.lower()
            # Lint tools first: "ruff check" is linting even though it says "check".
            if re.search(r"\b(lint|ruff|flake8|black|eslint|prettier|pre-commit|fmt|format|clippy|mypy)\b", lowered):
                bucket = lint
            elif re.search(r"\b(test|pytest|jest|vitest|tox|nox|check)\b", lowered):
                bucket = test
            else:
                bucket = setup
            if command not in bucket:
                bucket.append(command)

    return {"rules": found_rules, "setup_commands": setup[:4], "test_commands": test[:3], "lint_commands": lint[:3]}


def mentioned_paths(text: str) -> List[str]:
    return sorted(set(_PATH_RE.findall(text or "")))


def _path_words(path: str) -> set:
    return set(tokens(re.sub(r"[/._-]", " ", path)))


def likely_files(tree: List[dict], issue_title: str, issue_body: str, limit: int = 8) -> List[Dict[str, object]]:
    """Rank repo files by overlap with the issue's words. A starting point, not an answer.

    Words found in many paths (the package name, "src", "json") carry little signal, so each
    match is weighted by how rare the word is across the tree.
    """
    title_words = set(tokens(issue_title))
    words = title_words | set(tokens(issue_body)[:300])
    explicit = mentioned_paths(issue_title + "\n" + (issue_body or ""))
    files = [
        entry.get("path", "")
        for entry in tree
        if entry.get("type") == "blob" and not any(entry.get("path", "").startswith(d) or "/" + d in entry.get("path", "") for d in _SKIP_DIRS)
    ]
    path_words = {path: _path_words(path) for path in files}
    frequency: Dict[str, int] = {}
    for found in path_words.values():
        for word in found & words:
            frequency[word] = frequency.get(word, 0) + 1
    total = max(len(files), 1)

    ranked = []
    for path in files:
        lowered = path.lower()
        score = 0.0
        reasons = []
        for mention in explicit:
            if lowered.endswith(mention.lower()):
                score += 10
                reasons.append("named in the issue")
                break
        hits = sorted(w for w in path_words[path] & words if frequency[w] / total <= COMMON_WORD_SHARE or total < 10)
        if hits:
            # Title words are the strongest evidence; a lone body word is usually noise.
            score += sum(math.log(1 + total / frequency[w]) * (1.0 if w in title_words else 0.3) for w in hits)
            reasons.append("matches: " + ", ".join(hits[:4]))
            if not (title_words & set(hits)) and len(hits) < 2 and not reasons[0].startswith("named"):
                continue
        if score:
            if "test" in lowered:
                score -= 0.5
            ranked.append((score, path, reasons))
    ranked.sort(key=lambda item: (-item[0], len(item[1])))
    return [{"path": path, "why": "; ".join(reasons)} for _, path, reasons in ranked[:limit]]
