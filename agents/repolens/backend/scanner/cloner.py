"""
RepoLens — Repository Cloner

Shallow-clones a GitHub repository into a temporary directory.
Enforces:
  - Repository size limit while the clone is in progress
  - Wall-clock timeout
  - Commit SHA capture
  - Basic tech-stack detection
  - Reliable cleanup via context manager
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from backend.config import get_settings
from backend.scanner.validator import build_clone_args

logger = logging.getLogger(__name__)


class CloneError(RuntimeError):
    """Raised when cloning fails for any reason."""
    pass


@contextmanager
def cloned_repo(normalized_url: str) -> Generator[dict, None, None]:
    """
    Context manager that:
      1. Creates a temp dir
      2. Shallow-clones the repo
      3. Yields a dict with: path, commit_sha, tech_stack, repo_size_kb
      4. Always deletes the temp dir on exit

    Usage::

        with cloned_repo(url) as info:
            path = info["path"]
            sha  = info["commit_sha"]
    """
    settings = get_settings()
    tmp_dir = tempfile.mkdtemp(prefix="repolens_")
    clone_dst = os.path.join(tmp_dir, "repo")
    try:
        args = build_clone_args(normalized_url, clone_dst)
        logger.info("Cloning %s into %s", normalized_url, clone_dst)
        start = time.monotonic()
        limit_bytes = settings.max_repo_size_mb * 1024 * 1024
        deadline = start + settings.scan_timeout_seconds
        # Temporary files avoid unbounded memory use or full-pipe deadlocks
        # while the clone process is monitored for disk use.
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            process = subprocess.Popen(
                args,
                shell=False,
                stdout=stdout_file,
                stderr=stderr_file,
            )
            try:
                while process.poll() is None:
                    if time.monotonic() >= deadline:
                        _stop_process(process)
                        raise CloneError(
                            f"Clone timed out after {settings.scan_timeout_seconds}s."
                        )
                    if _dir_size_bytes(clone_dst) > limit_bytes:
                        _stop_process(process)
                        raise CloneError(
                            f"Repository exceeds the configured {settings.max_repo_size_mb} MB limit."
                        )
                    time.sleep(0.2)
            finally:
                if process.poll() is None:
                    _stop_process(process)
            stderr_file.seek(0)
            stderr = stderr_file.read().decode("utf-8", errors="replace")
            returncode = process.returncode
        # Catch a size-limit crossing between the last poll and process exit.
        if _dir_size_bytes(clone_dst) > limit_bytes:
            raise CloneError(
                f"Repository exceeds the configured {settings.max_repo_size_mb} MB limit."
            )
        elapsed = time.monotonic() - start

        if returncode != 0:
            raise CloneError(
                f"git clone failed (exit {returncode}): {stderr[-500:]}"
            )

        logger.info("Cloned in %.1fs", elapsed)

        commit_sha = _get_head_sha(clone_dst)
        tech_stack = _detect_tech_stack(clone_dst)
        repo_size_kb = _dir_size_bytes(clone_dst) // 1024

        yield {
            "path": clone_dst,
            "commit_sha": commit_sha,
            "tech_stack": tech_stack,
            "repo_size_kb": repo_size_kb,
            "clone_duration_s": elapsed,
        }
    except subprocess.TimeoutExpired as exc:
        raise CloneError(
            f"Clone timed out after {settings.scan_timeout_seconds}s."
        ) from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.debug("Cleaned up temp dir %s", tmp_dir)


def _stop_process(process: subprocess.Popen) -> None:
    """Stop and reap the clone process after a timeout or size-limit breach."""
    try:
        process.terminate()
    except ProcessLookupError:
        # The process may exit between poll() and terminate().
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        process.wait()


def _get_head_sha(repo_path: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "HEAD"],
            shell=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:40]
    except Exception as exc:
        logger.warning("Could not get HEAD SHA: %s", exc)
    return None


# Technology indicators: filename/extension -> label
_TECH_INDICATORS: dict[str, str] = {
    "package.json":          "Node.js",
    "requirements.txt":      "Python",
    "pyproject.toml":        "Python",
    "setup.py":              "Python",
    "Cargo.toml":            "Rust",
    "go.mod":                "Go",
    "pom.xml":               "Java (Maven)",
    "build.gradle":          "Java (Gradle)",
    "Gemfile":               "Ruby",
    "composer.json":         "PHP",
    "Dockerfile":            "Docker",
    "docker-compose.yml":    "Docker Compose",
    "docker-compose.yaml":   "Docker Compose",
    ".terraform":            "Terraform",
    "Chart.yaml":            "Helm",
    "pubspec.yaml":          "Dart/Flutter",
}


def _detect_tech_stack(repo_path: str) -> list[str]:
    """Walk top-level and one level deep to detect technology indicators."""
    detected: set[str] = set()
    base = Path(repo_path)
    for indicator, label in _TECH_INDICATORS.items():
        # Check root and one level of subdirectories
        if (base / indicator).exists():
            detected.add(label)
        for sub in base.iterdir():
            if sub.is_dir() and (sub / indicator).exists():
                detected.add(label)
    return sorted(detected)


def _dir_size_bytes(path: str) -> int:
    total = 0
    for dirpath, _dirs, filenames in os.walk(path):
        for fname in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, fname))
            except OSError:
                pass
    return total
