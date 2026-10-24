"""
RepoLens — Scan Orchestrator

Coordinates: validation → clone → scan → normalize → persist.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from backend.config import get_settings
from backend.models import AuditReport, Finding, ScannerStatus
from backend.scanner.validator import validate_github_url, ValidationError
from backend.scanner.cloner import cloned_repo, CloneError
from backend.scanner.trivy import run_trivy
from backend.scanner.semgrep import run_semgrep

logger = logging.getLogger(__name__)


class ScanError(RuntimeError):
    pass


def run_full_scan(raw_url: str) -> AuditReport:
    """
    Validate URL, clone, run scanners, and return a populated AuditReport.
    Does NOT persist to database — the caller (API route) is responsible.

    Raises:
        ValidationError — invalid URL
        CloneError     — clone failed
        ScanError      — unrecoverable internal error
    """
    settings = get_settings()
    t0 = time.monotonic()

    # 1. Validate URL
    normalized_url, repo_name = validate_github_url(raw_url)

    findings: list[Finding] = []
    scanner_status: dict[str, ScannerStatus] = {}
    commit_sha: Optional[str] = None
    tech_stack: list[str] = []

    # 2. Clone and scan
    with cloned_repo(normalized_url) as clone_info:
        commit_sha = clone_info["commit_sha"]
        tech_stack = clone_info["tech_stack"]
        repo_path = clone_info["path"]

        # 3. Trivy
        trivy_findings, trivy_status = run_trivy(repo_path)
        findings.extend(trivy_findings)
        scanner_status["trivy"] = trivy_status

        # 4. Semgrep
        semgrep_findings, semgrep_status = run_semgrep(repo_path)
        findings.extend(semgrep_findings)
        scanner_status["semgrep"] = semgrep_status

    elapsed = time.monotonic() - t0

    report = AuditReport(
        repository_url=normalized_url,
        repository_name=repo_name,
        commit_sha=commit_sha,
        tech_stack=tech_stack,
        findings=findings,
        scanner_status=scanner_status,
        ai_summary=None,
        ai_prioritized_actions=[],
        ai_available=False,
        is_demo=False,
        scan_duration_seconds=round(elapsed, 2),
        generated_at=datetime.now(timezone.utc),
    )

    return report


def _count_by_severity(findings: list[Finding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return counts
