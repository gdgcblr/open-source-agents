"""Unit tests for AST static safety validator."""

import pytest
from healer.ast_guard import validate_code_safety


def test_ast_guard_valid_safe_code():
    code = """
def calculate_metrics(items):
    total = sum(x['val'] for x in items if x.get('val'))
    return {"total": total, "count": len(items)}
"""
    is_safe, reason = validate_code_safety(code)
    assert is_safe is True
    assert "passed" in reason.lower()


def test_ast_guard_syntax_error():
    broken_syntax = "def broken_fn(a, b\n    return a +"
    is_safe, reason = validate_code_safety(broken_syntax)
    assert is_safe is False
    assert "Syntax error" in reason


@pytest.mark.parametrize("dangerous_snippet,expected_pattern", [
    ("import os\nos.system('dir')", "os.system"),
    ("import os\nos.popen('whoami')", "os.popen"),
    ("import subprocess\nsubprocess.call(['ls'])", "subprocess"),
    ("eval('2 + 2')", "eval()"),
    ("exec('print(1)')", "exec()"),
    ("__import__('os').system('ls')", "__import__"),
    ("import shutil\nshutil.rmtree('/tmp')", "shutil.rmtree"),
])
def test_ast_guard_blocks_dangerous_calls(dangerous_snippet, expected_pattern):
    is_safe, reason = validate_code_safety(dangerous_snippet)
    assert is_safe is False
    assert expected_pattern in reason
