import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _get_repo_slug(repo_root: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", repo_root, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        remote = result.stdout.strip()
    except Exception:
        return None

    if not remote:
        return None

    cleaned = remote.replace("git@github.com:", "https://github.com/")
    cleaned = cleaned.replace("ssh://git@github.com/", "https://github.com/")
    cleaned = cleaned.replace("git://github.com/", "https://github.com/")
    cleaned = cleaned.replace("https://github.com/", "")
    cleaned = cleaned.rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    if "/" not in cleaned:
        return None
    parts = [segment for segment in cleaned.split("/") if segment]
    if len(parts) < 2:
        return None
    return "/".join(parts[:2])


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "maintainer-guard",
    }
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _open_prs_for_repo(repo_slug: str) -> list[dict]:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo_slug}/pulls?state=open&per_page=50",
        headers=_github_headers(),
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8")
    data = json.loads(payload)
    return data if isinstance(data, list) else []


def _pr_files_for_repo(repo_slug: str, pr_number: int) -> list[str]:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo_slug}/pulls/{pr_number}/files",
        headers=_github_headers(),
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8")
    data = json.loads(payload)
    if not isinstance(data, list):
        return []
    return [item.get("filename", "") for item in data if isinstance(item, dict)]


def _jaccard_similarity(left: str, right: str) -> float:
    left_tokens = set(_normalize_text(left).split())
    right_tokens = set(_normalize_text(right).split())
    if not left_tokens and not right_tokens:
        return 0.0
    if not left_tokens or not right_tokens:
        return 0.0
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return len(left_tokens & right_tokens) / len(union)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def check_duplicate_prs(repo_root: str, diff_text: str, changed_files: list[str]) -> list[str]:
    """Check for open PRs that look like duplicate work based on overlap and scope similarity."""
    repo_slug = _get_repo_slug(repo_root)
    if not repo_slug:
        return []

    try:
        open_prs = _open_prs_for_repo(repo_slug)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        return []

    if not open_prs:
        return []

    normalized_changed_files = {Path(item).as_posix().lower() for item in changed_files if item}
    diff_fingerprint = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()
    drift_hint = _normalize_text(" ".join(changed_files) + " " + diff_text)

    candidate_prs = []
    for pr in open_prs:
        title = pr.get("title", "")
        branch_name = (pr.get("head") or {}).get("ref", "")
        pr_number = pr.get("number")
        created_at = pr.get("created_at")
        if not title or pr_number is None:
            continue

        try:
            pr_files = _pr_files_for_repo(repo_slug, int(pr_number))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
            pr_files = []

        file_overlap = bool(normalized_changed_files.intersection({Path(item).as_posix().lower() for item in pr_files if item}))
        scope_similarity = _jaccard_similarity(title, drift_hint) > 0.18 or _jaccard_similarity(branch_name, drift_hint) > 0.18
        same_diff_hash = hashlib.sha256((title + "\n" + "\n".join(pr_files)).encode("utf-8")).hexdigest() == diff_fingerprint

        if file_overlap or scope_similarity or same_diff_hash:
            candidate_prs.append({
                "number": int(pr_number),
                "title": title,
                "created_at": created_at,
                "timestamp": _parse_iso_datetime(created_at),
                "files": pr_files,
            })

    if not candidate_prs:
        return []

    # Sort to identify the later PR in overlapping work.
    candidate_prs.sort(key=lambda item: (item["timestamp"] or datetime.min.replace(tzinfo=timezone.utc), item["number"]))

    issues = []
    for idx in range(1, len(candidate_prs)):
        later_pr = candidate_prs[idx]
        earlier_pr = candidate_prs[idx - 1]
        if later_pr["timestamp"] is None or earlier_pr["timestamp"] is None:
            issues.append(
                f"POSSIBLE DUPLICATE PR: Open PR #{later_pr['number']} ('{later_pr['title']}') appears to overlap with an earlier open PR #{earlier_pr['number']} ('{earlier_pr['title']}'). Review the older PR first and close the later duplicate if it is the same change."
            )
            continue

        if later_pr["timestamp"] >= earlier_pr["timestamp"]:
            issues.append(
                f"POSSIBLE DUPLICATE PR: Open PR #{later_pr['number']} ('{later_pr['title']}') was opened later than PR #{earlier_pr['number']} ('{earlier_pr['title']}') and appears to cover the same scope. Maintainers should review the earlier PR first and treat the later one as a duplicate."
            )

    if not issues:
        # Fallback for a single overlapping PR, but still call out the likely duplication signal.
        first = candidate_prs[0]
        issues.append(
            f"POSSIBLE DUPLICATE PR: Open PR #{first['number']} ('{first['title']}') appears to overlap with this change and may already be in progress. Review it before processing a duplicate contribution."
        )

    return issues


def check_zero_secrets(diff_text: str) -> list[str]:
    """Scans the diff for potential accidental secrets or API keys."""
    violations = []
    secret_patterns = [
        r"(AIza[0-9A-Za-z-_]{35})",
        r"sk-[a-zA-Z0-9]{20,}",
        r"ghp_[a-zA-Z0-9]{36}",
        r"(?:aws|AWS)._?(?:access|secret)?_?key\s*[:=]\s*[A-Za-z0-9/+=]{16,}",
        r"xox[baprs]-[A-Za-z0-9-]{10,}",
    ]

    for pattern in secret_patterns:
        if re.search(pattern, diff_text, re.IGNORECASE):
            violations.append("SECURITY ALERT: Potential hardcoded API key or secret detected in diff!")
            break

    return violations


def validate_manifest_files(changed_files: list[str]) -> list[str]:
    """Checks if dependency changes are properly tracked."""
    violations = []
    has_code_changes = any(f.endswith((".py", ".js", ".ts")) for f in changed_files)
    has_manifest_changes = any(f in ["requirements.txt", "package.json", "pyproject.toml"] for f in changed_files)

    if has_code_changes and not has_manifest_changes:
        violations.append(
            "POLICY WARNING: Code files were modified, but no dependency manifest (requirements.txt/package.json) update was found."
        )

    return violations


def read_contributing_rules(repo_root: str) -> str:
    """Read the repository-level CONTRIBUTING.md file when present."""
    candidate_paths = [
        Path(repo_root) / "CONTRIBUTING.md",
        Path(repo_root) / ".github" / "CONTRIBUTING.md",
    ]

    for path in candidate_paths:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore")
    return ""


def check_contributing_compliance(repo_root: str, diff_text: str, changed_files: list[str]) -> list[str]:
    """Enforces project-specific rules declared in CONTRIBUTING.md when available."""
    violations = []
    rules = read_contributing_rules(repo_root)
    if not rules:
        return violations

    lower_rules = rules.lower()
    has_code_changes = any(f.endswith((".py", ".js", ".ts")) for f in changed_files)
    has_doc_changes = any(f.lower().endswith((".md", ".rst", ".txt")) for f in changed_files)

    if "documentation" in lower_rules and "required" in lower_rules and has_code_changes and not has_doc_changes:
        violations.append(
            "CONTRIBUTING POLICY: Code changes were made without an accompanying documentation update, which this repo requires."
        )

    if "branch naming" in lower_rules:
        branch_name = os.popen('git -C "%s" rev-parse --abbrev-ref HEAD 2>/dev/null' % repo_root).read().strip()
        if branch_name and branch_name not in ["", "HEAD"]:
            expected_prefixes = ["feat/", "feature/", "bugfix/", "hotfix/", "docs/"]
            if not any(branch_name.startswith(prefix) for prefix in expected_prefixes):
                violations.append(
                    f"CONTRIBUTING POLICY: Branch name '{branch_name}' does not follow the repository naming convention in CONTRIBUTING.md."
                )

    if "breaking change" in lower_rules and re.search(r"breaking change|breaking-change|BREAKING CHANGE", diff_text, re.IGNORECASE):
        violations.append(
            "CONTRIBUTING POLICY: Breaking change was detected and must be explicitly documented and approved."
        )

    if "changelog" in lower_rules and has_code_changes and not any(f.lower() in {"changelog.md", "CHANGELOG.md"} for f in changed_files):
        violations.append(
            "CONTRIBUTING POLICY: Repository policy requires a changelog entry for code changes."
        )

    return violations


def build_actionable_remediation(issues: list[str]) -> list[str]:
    """Produces copy-pasteable fixes for detected issues."""
    commands = []

    if any("secret" in issue.lower() for issue in issues):
        commands.extend([
            "git diff --check",
            "git restore --staged . && git checkout -- .",
            "grep -RInE 'AIza|ghp_|sk-[A-Za-z0-9]+' . || true",
            "cp .env.example .env && printf 'GEMINI_API_KEY=your_key_here\n' > .env",
        ])

    if any("manifest" in issue.lower() for issue in issues):
        commands.append("pip freeze > requirements.txt  # or update package.json / pyproject.toml for the dependency change")

    if any("documentation" in issue.lower() for issue in issues) or any("changelog" in issue.lower() for issue in issues):
        commands.append("printf '\n## Summary\n- Update docs/changelog for this fix.\n' >> README.md")

    if any("branch name" in issue.lower() for issue in issues):
        commands.append("git checkout -b feat/<your-project-slug>")

    if any("breaking change" in issue.lower() for issue in issues):
        commands.append("echo 'BREAKING CHANGE: document migration steps and note the release impact in docs.' >> CHANGELOG.md")

    if any("duplicate pr" in issue.lower() for issue in issues):
        commands.extend([
            "gh pr list --state open --limit 20",
            "gh pr view <PR_NUMBER> --comments",
            "git remote -v && git branch --show-current",
        ])

    return commands
