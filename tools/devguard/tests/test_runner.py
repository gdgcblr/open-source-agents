"""Unit tests for DevGuard safe command runner."""

import sys
import pytest
from devguard.runner import CommandResult, execute_command


def test_execute_echo_success():
    """Test running a standard echo command."""
    res = execute_command([sys.executable, "-c", "print('hello from runner')"])
    assert res.exit_code == 0
    assert "hello from runner" in res.stdout
    assert res.stderr == ""


def test_execute_failing_command():
    """Test running a command that exits with a non-zero code and writes to stderr."""
    res = execute_command([sys.executable, "-c", "import sys; sys.stderr.write('error occurred'); sys.exit(42)"])
    assert res.exit_code == 42
    assert "error occurred" in res.stderr


def test_execute_empty_args_raises_value_error():
    """Calling execute_command with empty args must raise ValueError."""
    with pytest.raises(ValueError, match="Cannot execute an empty command list"):
        execute_command([])


def test_execute_nonexistent_binary():
    """Executing a nonexistent binary should return exit code 127 with helpful stderr."""
    res = execute_command(["nonexistent_binary_xyz_12345"])
    assert res.exit_code == 127
    assert "Command not found" in res.stderr

