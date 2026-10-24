"""Code pointers: the exact lines an issue is probably about, with links.

Issues often name the code they are about in backticks (`html.escape`, `_storage`). We look
for those identifiers inside the files most likely to be involved and return line-numbered
matches. Read-only, bounded, and grounded: only files from the repo's own tree or GitHub's code
search are opened, and every pointer links to the line it came from.
"""

from __future__ import annotations

import base64
import re
from typing import Dict, List, Optional

from .github import GitHubError
from .related import STOPWORDS

MAX_FILES = 4
MAX_HITS_PER_FILE = 3
MAX_FILE_BYTES = 300_000
_CODE_SPAN_RE = re.compile(r"`([^`\n]{3,60})`")
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][\w.]*[A-Za-z0-9_]$")
_CAMEL_RE = re.compile(r"[a-z][A-Z]")
_COMMON = {"main", "master", "true", "false", "null", "none", "get", "post", "put", "delete", "json", "yaml", "html", "http", "https", "readme"}


def identifiers(title: str, body: str, limit: int = 8) -> List[str]:
    """Code-looking names in backticks, in the order the issue mentions them.

    Fenced code blocks are skipped: they are usually reproduction scripts, while the prose names
    the code that needs to change. The first names mentioned are usually the subject.
    """
    prose = _FENCE_RE.sub(" ", (title or "") + "\n" + (body or ""))
    found: List[str] = []
    for span in _CODE_SPAN_RE.findall(prose):
        span = span.strip().rstrip("()")
        if not _IDENTIFIER_RE.match(span) or span.lower() in _COMMON or span.lower() in STOPWORDS:
            continue
        if re.fullmatch(r"[0-9a-f]{7,40}", span):  # commit hashes
            continue
        # Plain words ("confluence") match far too much; require a code shape.
        if not ("_" in span or "." in span or _CAMEL_RE.search(span)):
            continue
        if span not in found:
            found.append(span)
    return found[:limit]


MAX_CODE_SEARCHES = 3


def _search_files(client, repo: str, names: List[str]) -> List[str]:
    """Ask GitHub code search which files contain the names. Needs a token.

    Code search tokenises on dots, so `html.escape` rarely matches; names with underscores
    (`_export_view`) are the most reliable, so they are tried first, unquoted.
    """
    if not client.authenticated or not names:
        return []
    ordered = [n for n in names if "_" in n] + [n for n in names if "_" not in n]
    for name in ordered[:MAX_CODE_SEARCHES]:
        try:
            items = client.search_code("repo:%s %s" % (repo, name), per_page=5)
        except GitHubError:
            return []
        paths = [item.get("path", "") for item in items if item.get("path")]
        if paths:
            return paths
    return []


def _read(client, repo: str, path: str, ref: str) -> Optional[str]:
    try:
        data = client.get_file(repo, path, ref)
    except GitHubError:
        return None
    if not isinstance(data, dict) or data.get("encoding") != "base64" or data.get("size", 0) > MAX_FILE_BYTES:
        return None
    try:
        return base64.b64decode(data.get("content", "")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None  # binary file


def code_pointers(client, repo: str, ref: str, title: str, body: str,
                  likely_paths: List[str], tree_paths: List[str]) -> Dict[str, object]:
    """Return {"identifiers": [...], "pointers": [{path, line, code, term, url}], "searched_files": [...]}."""
    names = identifiers(title, body)
    result: Dict[str, object] = {"identifiers": names, "pointers": [], "searched_files": []}
    if not names:
        return result

    known = set(tree_paths)
    files: List[str] = []
    for path in _search_files(client, repo, names) + list(likely_paths):
        # Guardrail: only open files that really exist in this repo's tree.
        if path and path not in files and (not known or path in known):
            files.append(path)
    files = files[:MAX_FILES]
    result["searched_files"] = files

    # On each line, report the most specific name it contains (`body.export_view` over `_view`).
    by_specificity = sorted(names, key=len, reverse=True)
    pointers = []
    for path in files:
        text = _read(client, repo, path, ref)
        if text is None:
            continue
        hits = 0
        for number, line in enumerate(text.splitlines(), 1):
            term = next((name for name in by_specificity if name in line), None)
            if not term:
                continue
            pointers.append({
                "path": path,
                "line": number,
                "code": line.strip()[:160],
                "term": term,
                "url": "https://github.com/%s/blob/%s/%s#L%d" % (repo, ref, path, number),
            })
            hits += 1
            if hits >= MAX_HITS_PER_FILE:
                break
    result["pointers"] = pointers
    return result
