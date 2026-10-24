"""Unit tests for sandboxed command execution and timeout enforcement."""

import sys
import pytest
from healer.sandbox import run_sandboxed_command


def test_sandbox_success():
    res = run_sandboxed_command(f'"{sys.executable}" -c "print(\'Sandbox OK\')"')
    assert res["passed"] is True
    assert res["exit_code"] == 0
    assert "Sandbox OK" in res["stdout"]


def test_sandbox_failing_command():
    res = run_sandboxed_command(f'"{sys.executable}" -c "import sys; sys.exit(42)"')
    assert res["passed"] is False
    assert res["exit_code"] == 42


def test_sandbox_timeout_enforcement():
    # Attempt to sleep for 5 seconds with a 1 second timeout
    res = run_sandboxed_command(
        f'"{sys.executable}" -c "import time; time.sleep(5)"',
        timeout=1
    )
    assert res["passed"] is False
    assert res["exit_code"] == -1
    assert "timed out" in res["stderr"]
