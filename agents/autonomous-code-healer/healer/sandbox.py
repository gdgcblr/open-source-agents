"""Sandboxed subprocess test execution environment with strict timeout limits."""

import logging
import os
import subprocess
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10


def run_sandboxed_command(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Runs a test or execution command in an isolated subprocess with hard timeout bounds.

    Args:
        command: Command string to execute (e.g., 'python -m pytest test_math.py').
        cwd: Working directory for command execution.
        timeout: Maximum seconds allowed before killing the subprocess.

    Returns:
        Dictionary with passed, exit_code, stdout, stderr, duration, and timed_out flags.
    """
    clean_cmd = str(command).strip()
    work_dir = os.path.abspath(cwd) if cwd else os.getcwd()
    safe_timeout = max(1, min(int(timeout or DEFAULT_TIMEOUT), 60))

    logger.info(f"[Sandbox] Executing: '{clean_cmd}' in {work_dir} (timeout={safe_timeout}s)")
    start_time = time.perf_counter()

    try:
        proc = subprocess.run(
            clean_cmd,
            cwd=work_dir,
            shell=True,
            capture_output=True,
            text=True,
            timeout=safe_timeout,
            encoding="utf-8",
            errors="replace"
        )
        duration = round(time.perf_counter() - start_time, 2)
        passed = (proc.returncode == 0)

        return {
            "passed": passed,
            "exit_code": proc.returncode,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
            "timed_out": False,
            "duration_seconds": duration,
        }

    except subprocess.TimeoutExpired as e:
        duration = round(time.perf_counter() - start_time, 2)
        logger.warning(f"[Sandbox] Command timed out after {safe_timeout}s: '{clean_cmd}'")
        return {
            "passed": False,
            "exit_code": -1,
            "stdout": (e.stdout or "") if hasattr(e, "stdout") else "",
            "stderr": f"Execution halted: Process timed out after {safe_timeout} seconds (anti-infinite-loop guard).",
            "timed_out": True,
            "duration_seconds": duration,
        }

    except Exception as e:
        duration = round(time.perf_counter() - start_time, 2)
        logger.error(f"[Sandbox] Execution error for '{clean_cmd}': {e}")
        return {
            "passed": False,
            "exit_code": 1,
            "stdout": "",
            "stderr": f"Subprocess launch error: {str(e)}",
            "timed_out": False,
            "duration_seconds": duration,
        }
