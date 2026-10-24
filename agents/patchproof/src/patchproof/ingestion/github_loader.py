"""Read-only GitHub PR ingestion with URL allowlist, SSRF protection, and bounds."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from patchproof.config import PatchProofConfig
from patchproof.core.enums import EvidenceKind, SourceKind, TrustLevel
from patchproof.core.ledger import EvidenceLedger, compute_sha256
from patchproof.core.models import SourceRef, utc_now_iso
from patchproof.ingestion.snapshot import ContextSnapshot, FileSnapshot

ALLOWED_GITHUB_WEB_HOSTS: frozenset[str] = frozenset({"github.com", "www.github.com"})
GITHUB_API_BASE_URL = "https://api.github.com"

_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_PR_PATH_RE = re.compile(
    r"^/([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100})/pull/([1-9]\d{0,9})/?$"
)
_ISSUE_REF_RE = re.compile(r"(?:fixes|closes|resolves)\s+#([1-9]\d{0,9})\b", re.IGNORECASE)
_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


class GitHubIngestionError(ValueError):
    """Base error raised when a GitHub PR cannot be safely validated or fetched."""


class GitHubURLValidationError(GitHubIngestionError):
    """Raised when a pull request URL violates the GitHub host, scheme, or SSRF policy."""


class GitHubRateLimitError(GitHubIngestionError):
    """Raised when GitHub API rate-limits or blocks the read-only request."""


@dataclass(frozen=True)
class ParsedGitHubPRUrl:
    """Validated components of a public GitHub Pull Request URL."""

    owner: str
    repo: str
    pull_number: int
    canonical_url: str


def _is_ip_literal(hostname: str) -> bool:
    """Return True if hostname is an IPv4 or IPv6 address literal."""
    cleaned = hostname.strip("[]")
    try:
        ipaddress.ip_address(cleaned)
        return True
    except ValueError:
        return False


def parse_github_pr_url(url: str) -> ParsedGitHubPRUrl:
    """Validate and parse a public GitHub Pull Request URL.

    Enforces:
    - HTTPS scheme only
    - No userinfo/credentials in URL
    - No query string or fragment tricks
    - Host strictly in ALLOWED_GITHUB_WEB_HOSTS (rejects IP literals, localhost, private hosts)
    - Path strictly matching `/<owner>/<repo>/pull/<number>` without traversal
    """
    if not url or not url.strip():
        raise GitHubURLValidationError("Pull request URL must not be empty")

    raw = url.strip()
    parsed = urlparse(raw)

    if parsed.scheme.lower() != "https":
        raise GitHubURLValidationError(
            f"Unsupported URL scheme '{parsed.scheme}': only 'https' is allowed"
        )

    if parsed.username or parsed.password:
        raise GitHubURLValidationError("Credentials in pull request URL are not allowed")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise GitHubURLValidationError("Pull request URL is missing a hostname")

    if _is_ip_literal(hostname):
        raise GitHubURLValidationError(
            f"IP address literals are forbidden (SSRF guard): {hostname}"
        )

    if hostname not in ALLOWED_GITHUB_WEB_HOSTS:
        raise GitHubURLValidationError(
            f"Untrusted host '{hostname}': only 'github.com' is allowed"
        )

    if parsed.port not in (None, 443):
        raise GitHubURLValidationError(f"Non-standard port '{parsed.port}' is not allowed")

    if ".." in parsed.path or "\\" in parsed.path:
        raise GitHubURLValidationError("Path traversal characters in URL path are forbidden")

    m = _PR_PATH_RE.match(parsed.path)
    if not m:
        raise GitHubURLValidationError(
            f"URL path '{parsed.path}' does not match expected "
            "'/<owner>/<repo>/pull/<number>' shape"
        )

    owner, repo, num_str = m.group(1), m.group(2), m.group(3)
    if repo.endswith(".git"):
        repo = repo[:-4]
    if owner in {".", ".."} or repo in {".", ".."}:
        raise GitHubURLValidationError("Invalid owner or repository name")
    if not (_OWNER_REPO_RE.match(owner) and _OWNER_REPO_RE.match(repo)):
        raise GitHubURLValidationError("Owner or repository contains disallowed characters")

    pull_number = int(num_str)
    canonical_url = f"https://github.com/{owner}/{repo}/pull/{pull_number}"
    return ParsedGitHubPRUrl(
        owner=owner,
        repo=repo,
        pull_number=pull_number,
        canonical_url=canonical_url,
    )


def _safe_get_json(
    client: httpx.Client,
    path: str,
    *,
    params: dict[str, str | int] | None = None,
    max_response_bytes: int = 1_048_576,
) -> Any:
    """Perform a strictly read-only GET request to api.github.com without following redirects."""
    if not path.startswith("/repos/"):
        raise GitHubURLValidationError(f"Refusing non-repository API path: {path}")

    url = f"{GITHUB_API_BASE_URL}{path}"
    try:
        response = client.request("GET", url, params=params, follow_redirects=False)
    except httpx.HTTPError as exc:
        raise GitHubIngestionError(f"Network error contacting GitHub API: {exc}") from exc

    if 300 <= response.status_code < 400:
        location = response.headers.get("location", "unknown")
        raise GitHubURLValidationError(
            f"Redirect responses ({response.status_code} -> {location}) are blocked by SSRF policy"
        )

    if response.status_code in {403, 429}:
        remaining = response.headers.get("x-ratelimit-remaining", "")
        if response.status_code == 429 or remaining == "0":
            raise GitHubRateLimitError(
                f"GitHub API rate limit exceeded (HTTP {response.status_code}). "
                "Configure read-only GITHUB_TOKEN or use offline fixture mode."
            )
        raise GitHubIngestionError(
            f"GitHub API access forbidden (HTTP 403) for '{path}'. "
            "Ensure the repository is public."
        )

    if response.status_code == 404:
        raise GitHubIngestionError(f"GitHub resource not found (HTTP 404) at '{path}'")

    if response.status_code != 200:
        raise GitHubIngestionError(
            f"Unexpected GitHub API status HTTP {response.status_code} for '{path}'"
        )

    raw_bytes = response.content
    if len(raw_bytes) > max_response_bytes:
        raise GitHubIngestionError(
            f"GitHub API response for '{path}' exceeded max_response_bytes ({max_response_bytes})"
        )

    try:
        return response.json()
    except ValueError as exc:
        raise GitHubIngestionError(f"Malformed JSON payload from GitHub API for '{path}'") from exc


def _decode_github_contents_payload(
    payload: Any,
    max_bytes: int,
) -> tuple[str, bool, int] | None:
    """Decode a GitHub `/contents/{path}` JSON object into bounded UTF-8 text."""
    if not isinstance(payload, dict):
        return None
    if payload.get("type") != "file":
        return None
    encoding = payload.get("encoding")
    raw_content = payload.get("content")
    if encoding != "base64" or not isinstance(raw_content, str):
        return None
    try:
        decoded_bytes = base64.b64decode(raw_content, validate=False)
    except Exception:
        return None
    orig_len = len(decoded_bytes)
    if orig_len > max_bytes:
        return decoded_bytes[:max_bytes].decode("utf-8", errors="ignore"), True, orig_len
    return decoded_bytes.decode("utf-8", errors="replace"), False, orig_len


def load_github_pr_snapshot(
    pull_request_url: str,
    config: PatchProofConfig,
    ledger: EvidenceLedger,
    *,
    http_client: httpx.Client | None = None,
) -> ContextSnapshot:
    """Fetch a public GitHub Pull Request (read-only) into an immutable ContextSnapshot."""
    parsed_pr = parse_github_pr_url(pull_request_url)
    repo_slug = f"{parsed_pr.owner}/{parsed_pr.repo}"
    base_api_path = f"/repos/{parsed_pr.owner}/{parsed_pr.repo}"

    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "PatchProof-Verifier/0.1 (read-only)",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    owns_client = http_client is None
    client = http_client or httpx.Client(
        headers=headers,
        timeout=httpx.Timeout(15.0, connect=5.0),
        follow_redirects=False,
    )

    try:
        pr_data = _safe_get_json(client, f"{base_api_path}/pulls/{parsed_pr.pull_number}")
        if not isinstance(pr_data, dict):
            raise GitHubIngestionError("Pull request metadata payload must be a JSON object")

        pr_title = str(pr_data.get("title") or "")
        pr_body = str(pr_data.get("body") or "")

        raw_base = pr_data.get("base")
        raw_head = pr_data.get("head")
        base_obj: dict[str, Any] = raw_base if isinstance(raw_base, dict) else {}
        head_obj: dict[str, Any] = raw_head if isinstance(raw_head, dict) else {}
        base_sha = str(base_obj.get("sha")) if base_obj.get("sha") else None
        head_sha = str(head_obj.get("sha")) if head_obj.get("sha") else None

        if base_sha and not _SHA_RE.match(base_sha):
            base_sha = None
        if head_sha and not _SHA_RE.match(head_sha):
            head_sha = None

        raw_labels_val = pr_data.get("labels")
        raw_labels: list[Any] = raw_labels_val if isinstance(raw_labels_val, list) else []
        labels: list[str] = []
        for lbl in raw_labels[: config.max_comments]:
            if isinstance(lbl, dict) and isinstance(lbl.get("name"), str):
                labels.append(lbl["name"])

        warnings: list[str] = []
        truncated = False
        total_context_bytes = 0

        # Optionally fetch linked issue if PR body references `Fixes #N`
        issue_title = ""
        issue_body = ""
        issue_match = _ISSUE_REF_RE.search(f"{pr_title}\n{pr_body}")
        if issue_match:
            issue_num = int(issue_match.group(1))
            try:
                issue_data = _safe_get_json(client, f"{base_api_path}/issues/{issue_num}")
                if isinstance(issue_data, dict):
                    issue_title = str(issue_data.get("title") or "")
                    issue_body = str(issue_data.get("body") or "")
            except GitHubIngestionError as exc:
                warnings.append(f"Referenced issue #{issue_num} could not be fetched: {exc}")

        # Fetch changed files list (bounded to max_source_files)
        files_data = _safe_get_json(
            client,
            f"{base_api_path}/pulls/{parsed_pr.pull_number}/files",
            params={"per_page": min(100, config.max_source_files + 5)},
        )
        if not isinstance(files_data, list):
            raise GitHubIngestionError("Pull request files payload must be a JSON array")

        diff_parts: list[str] = []
        diff_truncated = False
        changed_file_entries: list[dict[str, Any]] = []
        omitted_files_count = 0

        for entry in files_data:
            if not isinstance(entry, dict):
                continue
            filename = str(entry.get("filename") or "").strip().replace("\\", "/")
            if not filename or filename.startswith("/") or ".." in filename.split("/"):
                warnings.append(f"Skipped unsafe file path in PR file list: '{filename}'")
                omitted_files_count += 1
                continue
            changed_file_entries.append(entry)
            patch_str = str(entry.get("patch") or "")
            if patch_str:
                hunk_header = f"--- a/{filename}\n+++ b/{filename}\n{patch_str}"
                diff_parts.append(hunk_header)

        full_diff_text = "\n".join(diff_parts)
        encoded_diff = full_diff_text.encode("utf-8", errors="replace")
        if len(encoded_diff) > config.max_diff_bytes:
            diff_text = encoded_diff[: config.max_diff_bytes].decode("utf-8", errors="ignore")
            diff_truncated = True
            truncated = True
            warnings.append(
                f"PR diff exceeded max_diff_bytes ({config.max_diff_bytes}) and was truncated"
            )
        else:
            diff_text = full_diff_text
        total_context_bytes += len(diff_text.encode("utf-8"))

        # Record ISSUE_TEXT, PR_TEXT, and DIFF evidence
        issue_evidence_id: str | None = None
        if issue_title or issue_body:
            full_issue = f"{issue_title}\n\n{issue_body}".strip()
            ev_issue = ledger.append(
                kind=EvidenceKind.ISSUE_TEXT,
                source_uri=f"{parsed_pr.canonical_url}#issue",
                path="issue.md",
                line_start=1,
                line_end=max(1, len(full_issue.splitlines())),
                content=full_issue,
                trust_level=TrustLevel.UNTRUSTED_REPO_DATA,
                metadata={"synthetic": False},
            )
            issue_evidence_id = ev_issue.evidence_id

        pr_evidence_id: str | None = None
        if pr_title or pr_body:
            full_pr = f"{pr_title}\n\n{pr_body}".strip()
            ev_pr = ledger.append(
                kind=EvidenceKind.PR_TEXT,
                source_uri=parsed_pr.canonical_url,
                path="pr.md",
                line_start=1,
                line_end=max(1, len(full_pr.splitlines())),
                content=full_pr,
                trust_level=TrustLevel.UNTRUSTED_REPO_DATA,
                metadata={"synthetic": False},
            )
            pr_evidence_id = ev_pr.evidence_id

        diff_evidence_id: str | None = None
        if diff_text:
            ev_diff = ledger.append(
                kind=EvidenceKind.DIFF,
                source_uri=f"{parsed_pr.canonical_url}/files",
                path="diff.patch",
                line_start=1,
                line_end=max(1, len(diff_text.splitlines())),
                content=diff_text,
                trust_level=TrustLevel.UNTRUSTED_REPO_DATA,
                metadata={"truncated": diff_truncated, "synthetic": False},
            )
            diff_evidence_id = ev_diff.evidence_id

        # Fetch bounded file contents at head_sha for changed Python/source/test files
        source_files: dict[str, FileSnapshot] = {}
        test_files: dict[str, FileSnapshot] = {}
        source_evidence_ids: dict[str, str] = {}
        test_evidence_ids: dict[str, str] = {}
        loaded_count = 0

        for entry in changed_file_entries:
            filename = str(entry.get("filename")).replace("\\", "/")
            status_str = str(entry.get("status") or "modified")
            if status_str == "removed":
                continue
            if loaded_count >= config.max_source_files:
                omitted_files_count += 1
                truncated = True
                warnings.append(
                    f"Omitted file '{filename}' due to max_source_files={config.max_source_files}"
                )
                continue

            file_content: str | None = None
            file_trunc = False
            orig_bytes = 0

            if head_sha:
                try:
                    contents_payload = _safe_get_json(
                        client,
                        f"{base_api_path}/contents/{filename}",
                        params={"ref": head_sha},
                    )
                    decoded = _decode_github_contents_payload(
                        contents_payload, config.max_file_bytes
                    )
                    if decoded is not None:
                        file_content, file_trunc, orig_bytes = decoded
                except GitHubIngestionError as exc:
                    warnings.append(f"Could not fetch full content for '{filename}': {exc}")

            if file_content is None:
                # Fall back to reconstructable added/context lines from unified patch if available
                raw_patch = str(entry.get("patch") or "")
                if not raw_patch:
                    omitted_files_count += 1
                    continue
                reconstructed_lines = [
                    ln[1:]
                    for ln in raw_patch.splitlines()
                    if not ln.startswith("---")
                    and not ln.startswith("+++")
                    and not ln.startswith("@@")
                    and not ln.startswith("-")
                ]
                file_content = "\n".join(reconstructed_lines) + "\n"
                orig_bytes = len(file_content.encode("utf-8"))

            content_bytes = len(file_content.encode("utf-8"))
            if total_context_bytes + content_bytes > config.max_total_context_bytes:
                omitted_files_count += 1
                truncated = True
                warnings.append(
                    f"Omitted file '{filename}' due to max_total_context_bytes="
                    f"{config.max_total_context_bytes}"
                )
                continue

            if file_trunc:
                truncated = True
                warnings.append(
                    f"File '{filename}' exceeded max_file_bytes ({config.max_file_bytes}) "
                    "and was truncated"
                )

            total_context_bytes += content_bytes
            loaded_count += 1
            lines = file_content.splitlines()
            snap = FileSnapshot(
                path=filename,
                content=file_content,
                content_hash=compute_sha256(file_content),
                truncated=file_trunc,
                original_bytes=orig_bytes,
                line_count=len(lines),
            )

            is_test = (
                filename.startswith("tests/")
                or "/tests/" in filename
                or filename.split("/")[-1].startswith("test_")
            )
            if is_test:
                test_files[filename] = snap
                ev_tst = ledger.append(
                    kind=EvidenceKind.TEST_SOURCE,
                    source_uri=f"{parsed_pr.canonical_url}/files#{filename}",
                    path=filename,
                    line_start=1,
                    line_end=max(1, len(lines)),
                    content=file_content,
                    trust_level=TrustLevel.UNTRUSTED_REPO_DATA,
                    metadata={"truncated": file_trunc, "synthetic": False},
                )
                test_evidence_ids[filename] = ev_tst.evidence_id
            else:
                source_files[filename] = snap
                ev_src = ledger.append(
                    kind=EvidenceKind.SOURCE,
                    source_uri=f"{parsed_pr.canonical_url}/files#{filename}",
                    path=filename,
                    line_start=1,
                    line_end=max(1, len(lines)),
                    content=file_content,
                    trust_level=TrustLevel.UNTRUSTED_REPO_DATA,
                    metadata={"truncated": file_trunc, "synthetic": False},
                )
                source_evidence_ids[filename] = ev_src.evidence_id

        warnings.extend(ledger.warnings())

        hasher = hashlib.sha256()
        hasher.update(f"repo:{repo_slug}\n".encode())
        hasher.update(f"pr_url:{parsed_pr.canonical_url}\n".encode())
        hasher.update(f"base:{base_sha}\nhead:{head_sha}\n".encode())
        hasher.update(f"issue:{issue_title}\n{issue_body}\n".encode())
        hasher.update(f"pr:{pr_title}\n{pr_body}\n".encode())
        hasher.update(f"diff:{diff_text}\n".encode())
        for k in sorted(source_files):
            hasher.update(f"src:{k}:{source_files[k].content_hash}\n".encode())
        for k in sorted(test_files):
            hasher.update(f"tst:{k}:{test_files[k].content_hash}\n".encode())
        snapshot_hash = f"sha256:{hasher.hexdigest()}"

        source_ref = SourceRef(
            kind=SourceKind.GITHUB,
            repository=repo_slug,
            pull_request_url=parsed_pr.canonical_url,
            base_sha=base_sha,
            head_sha=head_sha,
            snapshot_hash=snapshot_hash,
            truncated=truncated,
            synthetic=False,
            warnings=warnings,
        )

        return ContextSnapshot(
            source_ref=source_ref,
            issue_title=issue_title,
            issue_body=issue_body,
            pr_title=pr_title,
            pr_body=pr_body,
            labels=labels,
            diff_text=diff_text,
            diff_truncated=diff_truncated,
            source_files=source_files,
            test_files=test_files,
            omitted_files_count=omitted_files_count,
            fetched_at=utc_now_iso(),
            issue_evidence_id=issue_evidence_id,
            pr_evidence_id=pr_evidence_id,
            diff_evidence_id=diff_evidence_id,
            source_evidence_ids=source_evidence_ids,
            test_evidence_ids=test_evidence_ids,
        )
    finally:
        if owns_client:
            client.close()
