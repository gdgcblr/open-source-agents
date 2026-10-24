"""
RepoLens — Semgrep Scanner Integration

Invokes Semgrep as a subprocess with a safe argument array (never shell=True).
Handles missing Semgrep, timeouts, and malformed output honestly.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Any

from backend.config import get_settings
from backend.models import Finding, ScannerStatus
from backend.scanner.normalizer import normalize_semgrep

logger = logging.getLogger(__name__)

import os

_KNOWN_SEMGREP_PATHS = [
    "semgrep",
    "/opt/homebrew/bin/semgrep",
    "/usr/local/bin/semgrep",
    os.path.expanduser("~/Library/Python/3.9/bin/semgrep"),
    os.path.expanduser("~/.local/bin/semgrep"),
]


def _find_semgrep() -> str | None:
    for path in _KNOWN_SEMGREP_PATHS:
        found = shutil.which(path) or (path if os.path.isabs(path) and os.path.exists(path) else None)
        if found:
            return found
    return None


def semgrep_available() -> bool:
    return _find_semgrep() is not None


def run_semgrep(repo_path: str) -> tuple[list[Finding], ScannerStatus]:
    """
    Run Semgrep against *repo_path* using the auto ruleset.

    Returns:
        (findings, ScannerStatus)
    """
    settings = get_settings()
    semgrep_bin = _find_semgrep()

    if not semgrep_bin:
        logger.warning("Semgrep not found in PATH. Skipping Semgrep scan.")
        return [], ScannerStatus(
            available=False,
            error_message="semgrep binary not found in PATH",
            finding_count=0,
        )

    args = [
        semgrep_bin,
        "--config", "auto",
        "--json",
        "--no-git-ignore",         # scan all files regardless of .gitignore
        "--timeout", str(min(settings.scan_timeout_seconds, 120)),
        "--max-memory", "512",     # MB — prevent OOM
        "--",
        repo_path,
    ]

    logger.info("Running Semgrep: %s", " ".join(args[:6]) + " ...")
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
            error_message=f"Semgrep timed out after {settings.scan_timeout_seconds}s",
            finding_count=0,
        )
    except Exception as exc:
        return [], ScannerStatus(
            available=True,
            exit_code=-1,
            error_message=f"Semgrep invocation failed: {exc}",
            finding_count=0,
        )

    # Semgrep returns exit 0 (no findings), 1 (findings found), or >1 (error)
    if result.returncode > 1:
        return [], ScannerStatus(
            available=True,
            exit_code=result.returncode,
            error_message=f"Semgrep exited {result.returncode}: {result.stderr[:300]}",
            finding_count=0,
        )

    try:
        semgrep_json: dict[str, Any] = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return [], ScannerStatus(
            available=True,
            exit_code=result.returncode,
            error_message=f"Semgrep output is not valid JSON: {exc}",
            finding_count=0,
        )

    findings = normalize_semgrep(semgrep_json)
    return findings, ScannerStatus(
        available=True,
        exit_code=result.returncode,
        finding_count=len(findings),
    )
