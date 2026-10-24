"""Safe subprocess execution module for DevGuard."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    """Encapsulates the execution result of an executed command."""
    exit_code: int
    stdout: str
    stderr: str


def execute_command(args: list[str], timeout: int = 300) -> CommandResult:
    """Execute a command safely using subprocess without shell=True.

    Args:
        args: List of command arguments (e.g. ["git", "status"]).
        timeout: Maximum seconds to wait before terminating the subprocess.

    Returns:
        CommandResult containing return code, stdout, and stderr.

    Raises:
        ValueError: If args is empty.
        FileNotFoundError: If the binary is not found on the system PATH.
        subprocess.TimeoutExpired: If the process exceeds the timeout limit.
    """
    if not args:
        raise ValueError("Cannot execute an empty command list.")

    # Explicitly avoid shell=True to prevent shell injection vulnerabilities.
    try:
        proc = subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return CommandResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    except FileNotFoundError as exc:
        return CommandResult(
            exit_code=127,
            stdout="",
            stderr=f"Command not found: '{args[0]}'. Ensure it is installed and on your PATH.",
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            exit_code=124,
            stdout=exc.stdout or "" if isinstance(exc.stdout, str) else "",
            stderr=f"Command timed out after {timeout} seconds: {' '.join(args)}",
        )

