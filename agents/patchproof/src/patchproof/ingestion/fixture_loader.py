"""Safe fixture ingestion with path confinement, size bounds, and provenance."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from patchproof.config import PatchProofConfig
from patchproof.core.enums import EvidenceKind, SourceKind, TrustLevel
from patchproof.core.ledger import EvidenceLedger, compute_sha256
from patchproof.core.models import SourceRef, utc_now_iso
from patchproof.ingestion.snapshot import ContextSnapshot, FileSnapshot

_FIXTURE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class FixtureIngestionError(ValueError):
    """Raised when a fixture cannot be safely loaded."""


class PathTraversalError(FixtureIngestionError):
    """Raised when a file path attempts traversal or symlink escape outside workspace."""


def resolve_confined_path(root: Path, relative_path: str) -> Path:
    """Resolve a relative path strictly inside root, rejecting traversal and symlink escape."""
    if not relative_path or not relative_path.strip():
        raise PathTraversalError("Empty file path is not allowed")

    normalized_str = relative_path.replace("\\", "/")
    if normalized_str.startswith("/") or re.match(r"^[A-Za-z]:", normalized_str):
        raise PathTraversalError(f"Absolute path is not allowed: {relative_path}")

    parts = [p for p in normalized_str.split("/") if p]
    if any(part in {".", ".."} for part in parts):
        raise PathTraversalError(f"Path traversal sequence rejected: {relative_path}")

    resolved_root = root.resolve()
    candidate = root.joinpath(*parts)

    # Check every ancestor up to candidate for symlinks escaping resolved_root
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            target = current.resolve()
            if not target.is_relative_to(resolved_root):
                raise PathTraversalError(
                    f"Symlink escape outside workspace rejected: {relative_path}"
                )

    resolved_candidate = candidate.resolve()
    if not resolved_candidate.is_relative_to(resolved_root):
        raise PathTraversalError(f"Resolved path escapes workspace root: {relative_path}")

    return resolved_candidate


def _read_bounded_text(path: Path, max_bytes: int) -> tuple[str, bool, int]:
    """Read UTF-8 text from path bounded to max_bytes."""
    raw = path.read_bytes()
    original_len = len(raw)
    if original_len > max_bytes:
        text = raw[:max_bytes].decode("utf-8", errors="ignore")
        return text, True, original_len
    return raw.decode("utf-8", errors="replace"), False, original_len


def load_fixture_snapshot(
    fixture_id: str,
    config: PatchProofConfig,
    ledger: EvidenceLedger,
) -> ContextSnapshot:
    """Load a local fixture into an immutable ContextSnapshot and populate the EvidenceLedger."""
    if not _FIXTURE_ID_RE.match(fixture_id):
        raise PathTraversalError(f"Invalid fixture_id '{fixture_id}'")

    fixtures_root = config.fixtures_dir.resolve()
    if not fixtures_root.exists():
        raise FixtureIngestionError(f"Fixtures directory does not exist: {fixtures_root}")

    fixture_dir = resolve_confined_path(fixtures_root, fixture_id)
    if not fixture_dir.is_dir():
        raise FixtureIngestionError(f"Fixture '{fixture_id}' not found at {fixture_dir}")

    manifest_path = resolve_confined_path(fixture_dir, "fixture.json")
    if not manifest_path.is_file():
        raise FixtureIngestionError(f"Fixture manifest missing: {manifest_path}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FixtureIngestionError(f"Malformed fixture.json in '{fixture_id}': {exc}") from exc

    if not isinstance(manifest, dict):
        raise FixtureIngestionError("fixture.json root must be a JSON object")

    warnings: list[str] = []
    truncated = False
    total_context_bytes = 0

    repository = str(manifest.get("repository") or f"fixture/{fixture_id}")
    synthetic = bool(manifest.get("synthetic", True))
    base_sha = manifest.get("base_sha")
    head_sha = manifest.get("head_sha")

    issue_title = str(manifest.get("issue_title") or "")
    issue_body = str(manifest.get("issue_body") or "")
    if "issue_file" in manifest and manifest["issue_file"]:
        issue_path = resolve_confined_path(fixture_dir, str(manifest["issue_file"]))
        if issue_path.is_file():
            issue_body, issue_trunc, _ = _read_bounded_text(issue_path, config.max_file_bytes)
            if issue_trunc:
                truncated = True
                warnings.append(f"Issue file '{manifest['issue_file']}' truncated to byte bound")

    pr_title = str(manifest.get("pr_title") or "")
    pr_body = str(manifest.get("pr_body") or "")
    if "pr_file" in manifest and manifest["pr_file"]:
        pr_path = resolve_confined_path(fixture_dir, str(manifest["pr_file"]))
        if pr_path.is_file():
            pr_body, pr_trunc, _ = _read_bounded_text(pr_path, config.max_file_bytes)
            if pr_trunc:
                truncated = True
                warnings.append(f"PR file '{manifest['pr_file']}' truncated to byte bound")

    raw_labels = manifest.get("labels") or []
    labels = [str(lbl) for lbl in raw_labels[: config.max_comments] if isinstance(lbl, str)]

    diff_text = str(manifest.get("diff_text") or "")
    diff_truncated = False
    diff_rel_path: str | None = None
    if "diff_file" in manifest and manifest["diff_file"]:
        diff_rel_path = str(manifest["diff_file"])
        diff_path = resolve_confined_path(fixture_dir, diff_rel_path)
        if not diff_path.is_file():
            raise FixtureIngestionError(f"Declared diff_file not found: {diff_rel_path}")
        diff_text, diff_truncated, _ = _read_bounded_text(diff_path, config.max_diff_bytes)
    else:
        raw_diff_bytes = len(diff_text.encode("utf-8"))
        if raw_diff_bytes > config.max_diff_bytes:
            diff_text = diff_text.encode("utf-8")[: config.max_diff_bytes].decode(
                "utf-8", errors="ignore"
            )
            diff_truncated = True

    if diff_truncated:
        truncated = True
        warnings.append(
            f"Diff content exceeded max_diff_bytes ({config.max_diff_bytes}) and was truncated"
        )
    total_context_bytes += len(diff_text.encode("utf-8"))

    # Record ISSUE_TEXT, PR_TEXT, DIFF evidence
    issue_evidence_id: str | None = None
    if issue_title or issue_body:
        full_issue = f"{issue_title}\n\n{issue_body}".strip()
        line_cnt = max(1, len(full_issue.splitlines()))
        ev_issue = ledger.append(
            kind=EvidenceKind.ISSUE_TEXT,
            source_uri=f"fixture://{fixture_id}/issue",
            path=str(manifest.get("issue_file") or "issue.md"),
            line_start=1,
            line_end=line_cnt,
            content=full_issue,
            trust_level=TrustLevel.UNTRUSTED_REPO_DATA,
            metadata={"synthetic": synthetic},
        )
        issue_evidence_id = ev_issue.evidence_id

    pr_evidence_id: str | None = None
    if pr_title or pr_body:
        full_pr = f"{pr_title}\n\n{pr_body}".strip()
        line_cnt = max(1, len(full_pr.splitlines()))
        ev_pr = ledger.append(
            kind=EvidenceKind.PR_TEXT,
            source_uri=f"fixture://{fixture_id}/pr",
            path=str(manifest.get("pr_file") or "pr.md"),
            line_start=1,
            line_end=line_cnt,
            content=full_pr,
            trust_level=TrustLevel.UNTRUSTED_REPO_DATA,
            metadata={"synthetic": synthetic},
        )
        pr_evidence_id = ev_pr.evidence_id

    diff_evidence_id: str | None = None
    if diff_text:
        line_cnt = max(1, len(diff_text.splitlines()))
        ev_diff = ledger.append(
            kind=EvidenceKind.DIFF,
            source_uri=f"fixture://{fixture_id}/{diff_rel_path or 'diff.patch'}",
            path=diff_rel_path or "diff.patch",
            line_start=1,
            line_end=line_cnt,
            content=diff_text,
            trust_level=TrustLevel.UNTRUSTED_REPO_DATA,
            metadata={"truncated": diff_truncated, "synthetic": synthetic},
        )
        diff_evidence_id = ev_diff.evidence_id

    # Load source files and test files with count and byte bounds
    declared_sources = list(manifest.get("source_files") or [])
    declared_tests = list(manifest.get("test_files") or [])

    source_files: dict[str, FileSnapshot] = {}
    test_files: dict[str, FileSnapshot] = {}
    source_evidence_ids: dict[str, str] = {}
    test_evidence_ids: dict[str, str] = {}
    omitted_files_count = 0
    loaded_files_count = 0

    for rel in declared_sources:
        rel_str = str(rel).replace("\\", "/")
        if loaded_files_count >= config.max_source_files:
            omitted_files_count += 1
            truncated = True
            warnings.append(
                f"Omitted source file '{rel_str}' due to max_source_files={config.max_source_files}"
            )
            continue
        file_path = resolve_confined_path(fixture_dir, rel_str)
        if not file_path.is_file():
            omitted_files_count += 1
            warnings.append(f"Declared source file '{rel_str}' was unavailable")
            continue
        content, file_trunc, orig_bytes = _read_bounded_text(file_path, config.max_file_bytes)
        content_bytes = len(content.encode("utf-8"))
        if total_context_bytes + content_bytes > config.max_total_context_bytes:
            omitted_files_count += 1
            truncated = True
            warnings.append(
                f"Omitted source file '{rel_str}' due to max_total_context_bytes="
                f"{config.max_total_context_bytes}"
            )
            continue
        if file_trunc:
            truncated = True
            warnings.append(
                f"Source file '{rel_str}' exceeded max_file_bytes ({config.max_file_bytes}) "
                "and was truncated"
            )
        total_context_bytes += content_bytes
        loaded_files_count += 1
        lines = content.splitlines()
        line_cnt = max(1, len(lines))
        snap = FileSnapshot(
            path=rel_str,
            content=content,
            content_hash=compute_sha256(content),
            truncated=file_trunc,
            original_bytes=orig_bytes,
            line_count=len(lines),
        )
        source_files[rel_str] = snap
        ev_src = ledger.append(
            kind=EvidenceKind.SOURCE,
            source_uri=f"fixture://{fixture_id}/{rel_str}",
            path=rel_str,
            line_start=1,
            line_end=line_cnt,
            content=content,
            trust_level=TrustLevel.UNTRUSTED_REPO_DATA,
            metadata={"truncated": file_trunc, "synthetic": synthetic},
        )
        source_evidence_ids[rel_str] = ev_src.evidence_id

    for rel in declared_tests:
        rel_str = str(rel).replace("\\", "/")
        if loaded_files_count >= config.max_source_files:
            omitted_files_count += 1
            truncated = True
            warnings.append(
                f"Omitted test file '{rel_str}' due to max_source_files={config.max_source_files}"
            )
            continue
        file_path = resolve_confined_path(fixture_dir, rel_str)
        if not file_path.is_file():
            omitted_files_count += 1
            warnings.append(f"Declared test file '{rel_str}' was unavailable")
            continue
        content, file_trunc, orig_bytes = _read_bounded_text(file_path, config.max_file_bytes)
        content_bytes = len(content.encode("utf-8"))
        if total_context_bytes + content_bytes > config.max_total_context_bytes:
            omitted_files_count += 1
            truncated = True
            warnings.append(
                f"Omitted test file '{rel_str}' due to max_total_context_bytes="
                f"{config.max_total_context_bytes}"
            )
            continue
        if file_trunc:
            truncated = True
            warnings.append(
                f"Test file '{rel_str}' exceeded max_file_bytes ({config.max_file_bytes}) "
                "and was truncated"
            )
        total_context_bytes += content_bytes
        loaded_files_count += 1
        lines = content.splitlines()
        line_cnt = max(1, len(lines))
        snap = FileSnapshot(
            path=rel_str,
            content=content,
            content_hash=compute_sha256(content),
            truncated=file_trunc,
            original_bytes=orig_bytes,
            line_count=len(lines),
        )
        test_files[rel_str] = snap
        ev_tst = ledger.append(
            kind=EvidenceKind.TEST_SOURCE,
            source_uri=f"fixture://{fixture_id}/{rel_str}",
            path=rel_str,
            line_start=1,
            line_end=line_cnt,
            content=content,
            trust_level=TrustLevel.UNTRUSTED_REPO_DATA,
            metadata={"truncated": file_trunc, "synthetic": synthetic},
        )
        test_evidence_ids[rel_str] = ev_tst.evidence_id

    warnings.extend(ledger.warnings())

    # Compute deterministic snapshot hash over provenance + loaded hashes
    hasher = hashlib.sha256()
    hasher.update(f"repo:{repository}\n".encode())
    hasher.update(f"issue:{issue_title}\n{issue_body}\n".encode())
    hasher.update(f"pr:{pr_title}\n{pr_body}\n".encode())
    hasher.update(f"diff:{diff_text}\n".encode())
    for k in sorted(source_files):
        hasher.update(f"src:{k}:{source_files[k].content_hash}\n".encode())
    for k in sorted(test_files):
        hasher.update(f"tst:{k}:{test_files[k].content_hash}\n".encode())
    snapshot_hash = f"sha256:{hasher.hexdigest()}"

    source_ref = SourceRef(
        kind=SourceKind.FIXTURE,
        repository=repository,
        pull_request_url=None,
        base_sha=str(base_sha) if base_sha else None,
        head_sha=str(head_sha) if head_sha else None,
        snapshot_hash=snapshot_hash,
        truncated=truncated,
        synthetic=synthetic,
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

