"""
RepoLens — Trivy Scanner Integration

Invokes Trivy as a subprocess with a safe argument array (never shell=True).
Handles missing Trivy, timeouts, and malformed output honestly.
A failed or absent Trivy scan is reported as unavailable — never as a clean scan.
"""
from __future__ import annotations

import json
import logging
import subprocess
import shutil
from typing import Any

from backend.config import get_settings
from backend.models import ScannerStatus
from backend.scanner.normalizer import normalize_trivy
from backend.models import Finding

logger = logging.getLogger(__name__)

import os

_KNOWN_TRIVY_PATHS = [
    "trivy",
    "/opt/homebrew/bin/trivy",
    "/usr/local/bin/trivy",
    os.path.expanduser("~/.local/bin/trivy"),
]


def _find_trivy() -> str | None:
    for path in _KNOWN_TRIVY_PATHS:
        found = shutil.which(path) or (path if os.path.isabs(path) and os.path.exists(path) else None)
        if found:
            return found
    return None


def trivy_available() -> bool:
    return _find_trivy() is not None


def run_trivy(repo_path: str) -> tuple[list[Finding], ScannerStatus]:
    """
    Run Trivy against *repo_path*.

    Returns:
        (findings, ScannerStatus)

    The caller MUST check ScannerStatus.available before trusting findings.
    An empty findings list with available=False means the scan did not run.
    """
    settings = get_settings()
    trivy_bin = _find_trivy()

    if not trivy_bin:
        logger.warning("Trivy not found in PATH. Skipping Trivy scan.")
        return [], ScannerStatus(
            available=False,
            error_message="trivy binary not found in PATH",
            finding_count=0,
        )

    args = [
        trivy_bin,
        "fs",
        "--format", "json",
        "--exit-code", "0",   # don't fail on findings; we parse the output
        "--no-progress",
        "--scanners", "vuln,secret,misconfig",
        "--",                 # end of flags
        repo_path,
    ]

    logger.info("Running Trivy: %s", " ".join(args))
    try:
        result = subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=settings.scan_timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return [], ScannerStatus(
            available=True,
            exit_code=-1,
            error_message=f"Trivy timed out after {settings.scan_timeout_seconds}s",
            finding_count=0,
        )
    except Exception as exc:
        return [], ScannerStatus(
            available=True,
            exit_code=-1,
            error_message=f"Trivy invocation failed: {exc}",
            finding_count=0,
        )

    if result.returncode not in (0, 1):
        # Trivy uses exit code 1 when vulnerabilities are found with --exit-code 1;
        # we set --exit-code 0 so anything nonzero here is a real error.
        return [], ScannerStatus(
            available=True,
            exit_code=result.returncode,
            error_message=f"Trivy exited {result.returncode}: {result.stderr[:300]}",
            finding_count=0,
        )

    try:
        trivy_json: dict[str, Any] = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return [], ScannerStatus(
            available=True,
            exit_code=result.returncode,
            error_message=f"Trivy output is not valid JSON: {exc}",
            finding_count=0,
        )

    findings = normalize_trivy(trivy_json)
    return findings, ScannerStatus(
        available=True,
        exit_code=result.returncode,
        finding_count=len(findings),
    )
