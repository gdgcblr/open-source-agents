"""GitHub REST API source for the triage command (stdlib urllib only)."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterator, Optional

from .models import AuditResult, Finding, Severity, Verdict

_BASE = "https://api.github.com"
_ACCEPT = "application/vnd.github+json"
_VERSION = "2022-11-28"

# Patterns reused from secrets rule (for scanning added diff lines)
_SECRET_QUICK_RE = re.compile(
    r"AIza[0-9A-Za-z\-_]{35}"           # Google
    r"|sk-[A-Za-z0-9]{20,}"              # OpenAI
    r"|(ghp|gho|ghs|ghr|github_pat)_[A-Za-z0-9_]{36,}"  # GitHub
    r"|AKIA[0-9A-Z]{16}"                 # AWS
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"  # PEM
    r"|xox[baprs]-[0-9A-Za-z\-]{10,}"   # Slack
)

_PLACEHOLDER_MARKERS = ("your_", "_here", "example", "placeholder", "xxxxxxxx", "<", ">", "...")

_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_GENERIC_NAMES = frozenset({"my-agent", "my-tool", "final-project", "final-test", "test", "demo", "helper"})
_MANIFESTS = frozenset({"requirements.txt", "pyproject.toml", "package.json", "Cargo.toml", "go.mod"})
_REQUIRED_FILES = frozenset({"README.md", ".env.example", ".gitignore"})

# Template example text for R10
_TEMPLATE_EXAMPLE = "Analysis completed:"

# README placeholder pattern
_PLACEHOLDER_RE = re.compile(
    r"\[(?:Project Name|One-sentence summary|your[- ]|Language Runtime|"
    r"Feature \d|Brief description|Explain what|Who is this|List the primary|"
    r"Provide a brief|Provide the exact|Explain how another|Be honest)\b",
    re.IGNORECASE,
)


def _is_placeholder(value: str) -> bool:
    low = value.lower()
    return any(m in low for m in _PLACEHOLDER_MARKERS)


def _redact(value: str) -> str:
    return value[:4] + "..." if len(value) > 4 else "****"


class RateLimitError(Exception):
    def __init__(self, reset_at: Optional[int] = None):
        self.reset_at = reset_at
        msg = "GitHub API rate limit reached."
        if reset_at:
            import datetime
            rt = datetime.datetime.fromtimestamp(reset_at).strftime("%H:%M:%S")
            msg += f" Resets at {rt}."
        super().__init__(msg)


class GitHubClient:
    def __init__(self, token: Optional[str] = None):
        self._token = token

    def _headers(self) -> dict:
        h = {"Accept": _ACCEPT, "X-GitHub-Api-Version": _VERSION}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _get(self, url: str, params: Optional[dict] = None) -> dict | list:
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query}"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 403:
                reset_at = int(e.headers.get("X-RateLimit-Reset", 0) or 0)
                raise RateLimitError(reset_at) from e
            if e.code == 404:
                raise FileNotFoundError(f"Not found: {url}") from e
            raise

    def list_open_prs(self, owner: str, repo: str, limit: int = 20) -> list[dict]:
        prs = []
        page = 1
        while len(prs) < limit:
            batch = self._get(
                f"{_BASE}/repos/{owner}/{repo}/pulls",
                {"state": "open", "per_page": min(30, limit - len(prs)), "page": page},
            )
            if not isinstance(batch, list) or not batch:
                break
            prs.extend(batch)
            page += 1
        return prs[:limit]

    def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        return self._get(f"{_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/files")  # type: ignore

    def get_file_content(self, owner: str, repo: str, path: str, ref: str = "main") -> Optional[str]:
        try:
            data = self._get(f"{_BASE}/repos/{owner}/{repo}/contents/{path}", {"ref": ref})
            if isinstance(data, dict) and data.get("encoding") == "base64":
                import base64
                return base64.b64decode(data["content"]).decode(errors="replace")
        except (FileNotFoundError, KeyError):
            pass
        return None


def _detect_project_dir(files: list[dict]) -> Optional[str]:
    """Guess the project directory from changed files (most-common agents/X or tools/X prefix)."""
    from collections import Counter
    prefixes: list[str] = []
    for f in files:
        fname = f.get("filename", "")
        parts = Path(fname).parts
        if len(parts) >= 2 and parts[0] in ("agents", "tools"):
            prefixes.append(str(Path(parts[0]) / parts[1]))
    if not prefixes:
        return None
    (most_common, _) = Counter(prefixes).most_common(1)[0]
    return most_common


def triage_pr(
    client: GitHubClient, owner: str, repo: str, pr: dict
) -> dict:
    """Run lightweight checks on a single PR (no clone). Returns a triage dict."""
    pr_number = pr["number"]
    author = pr.get("user", {}).get("login", "?")
    title = pr.get("title", "")

    findings: list[Finding] = []

    try:
        files = client.get_pr_files(owner, repo, pr_number)
    except Exception as exc:
        return {
            "pr": pr_number,
            "author": author,
            "title": title,
            "project_dir": "?",
            "verdict": Verdict.CHANGES_REQUESTED.value,
            "top_issues": [str(exc)],
        }

    project_dir = _detect_project_dir(files)
    project_slug = Path(project_dir).name if project_dir else None

    # R01: check location
    if not project_dir:
        findings.append(Finding(
            rule_id="R01", severity=Severity.ERROR, file=None, line=None,
            message="No files under agents/ or tools/ found.",
            evidence=None, fix_hint="Place your project under agents/<slug>/ or tools/<slug>/."))
    else:
        parts = Path(project_dir).parts
        if len(parts) != 2 or parts[0] not in ("agents", "tools"):
            findings.append(Finding(
                rule_id="R01", severity=Severity.ERROR, file=None, line=None,
                message=f"Project not a direct child of agents/ or tools/: {project_dir}",
                evidence=project_dir, fix_hint="Move to agents/<slug>/ or tools/<slug>/."))

    # R02+R03: naming
    if project_slug:
        if not _KEBAB_RE.fullmatch(project_slug):
            findings.append(Finding(
                rule_id="R02", severity=Severity.ERROR, file=None, line=None,
                message=f"Name '{project_slug}' is not lowercase kebab-case.",
                evidence=project_slug, fix_hint="Use lowercase-kebab-case."))
        if project_slug in _GENERIC_NAMES:
            findings.append(Finding(
                rule_id="R03", severity=Severity.ERROR, file=None, line=None,
                message=f"Name '{project_slug}' is too generic.",
                evidence=project_slug, fix_hint="Choose a descriptive name."))

    # R04: required files present in PR
    changed_filenames = {f["filename"] for f in files}
    if project_dir:
        for req in sorted(_REQUIRED_FILES):
            full = f"{project_dir}/{req}"
            if full not in changed_filenames:
                findings.append(Finding(
                    rule_id="R04", severity=Severity.WARNING, file=Path(full), line=None,
                    message=f"Required file '{req}' not in PR (may already exist in repo).",
                    evidence=None, fix_hint=f"Ensure {req} is committed."))
        has_manifest = any(
            f"{project_dir}/{m}" in changed_filenames for m in _MANIFESTS
        )
        if not has_manifest:
            findings.append(Finding(
                rule_id="R04", severity=Severity.WARNING, file=None, line=None,
                message="No manifest file (requirements.txt, etc.) in PR.",
                evidence=None, fix_hint="Add a dependency manifest."))

    # R07: scan added lines in patches for secrets
    for f in files:
        patch = f.get("patch", "")
        if not patch:
            continue
        for lineno, line in enumerate(patch.splitlines(), 1):
            if not line.startswith("+"):
                continue
            for m in _SECRET_QUICK_RE.finditer(line[1:]):
                val = m.group(0)
                if _is_placeholder(val):
                    continue
                findings.append(Finding(
                    rule_id="R07", severity=Severity.ERROR,
                    file=Path(f["filename"]), line=lineno,
                    message="Possible secret in added lines.",
                    evidence=_redact(val),
                    fix_hint="Remove secrets; use .env.example with placeholders only."))

    # R09: scope — files outside project_dir (allow one index edit)
    index_files = {"agents/README.md", "tools/README.md"}
    for f in files:
        fname = f["filename"]
        if project_dir and fname.startswith(project_dir + "/"):
            continue
        if fname in index_files:
            continue
        findings.append(Finding(
            rule_id="R09", severity=Severity.ERROR, file=Path(fname), line=None,
            message=f"Changed file outside project scope: {fname}",
            evidence=fname, fix_hint="Revert changes to files outside your project dir."))

    # R05: check README added lines for placeholders
    readme_file = f"{project_dir}/README.md" if project_dir else None
    readme_added_lines = []
    for f in files:
        if f["filename"] != readme_file:
            continue
        patch = f.get("patch", "")
        for lineno, line in enumerate(patch.splitlines(), 1):
            if not line.startswith("+"):
                continue
            content = line[1:]
            readme_added_lines.append(content)
            if _PLACEHOLDER_RE.search(content):
                findings.append(Finding(
                    rule_id="R05", severity=Severity.WARNING,
                    file=Path(f["filename"]), line=lineno,
                    message="README may contain leftover template placeholder.",
                    evidence=content.strip()[:60],
                    fix_hint="Fill in all template placeholders with real content."))
            if _TEMPLATE_EXAMPLE in content:
                findings.append(Finding(
                    rule_id="R10", severity=Severity.ERROR,
                    file=Path(f["filename"]), line=lineno,
                    message="README example section appears to be unmodified template text.",
                    evidence=content.strip()[:60],
                    fix_hint="Replace example output with a real run output."))

    readme_excerpt = "\n".join(readme_added_lines) if readme_added_lines else None

    # Compute verdict
    severities = {fi.severity for fi in findings}
    has_r07 = any(fi.rule_id == "R07" and fi.severity == Severity.ERROR for fi in findings)
    if has_r07:
        verdict = Verdict.REJECT
    elif Severity.ERROR in severities:
        verdict = Verdict.CHANGES_REQUESTED
    elif Severity.WARNING in severities:
        verdict = Verdict.APPROVE_WITH_NITS
    else:
        verdict = Verdict.READY

    top_issues = [f"{fi.rule_id}: {fi.message}" for fi in findings if fi.severity == Severity.ERROR][:3]

    return {
        "pr": pr_number,
        "author": author,
        "title": title[:60],
        "project_dir": project_dir or "?",
        "verdict": verdict.value,
        "top_issues": top_issues,
        "finding_count": len(findings),
        "readme_excerpt": readme_excerpt,
    }
