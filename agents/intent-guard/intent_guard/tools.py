"""Tools (functions) that the ADK agent can invoke during its review.

These deterministic tools provide factual, structural data to support the
agent's semantic correctness analysis.
"""

from __future__ import annotations

import ast


def parse_diff_metadata(code_diff: str) -> dict:
    """Analyze a unified git diff / patch to extract structural metadata:
    files modified or created, addition/deletion line counts, and patch hunks.

    Use this tool to get an objective inventory of every file touched and
    the scale of the changes before conducting line-by-line review.

    Args:
        code_diff: The raw unified git diff or patch text.

    Returns:
        A dictionary containing total files changed, addition count, deletion
        count, and per-file breakdown with hunk headers.
    """
    files = []
    current_file = None
    additions = 0
    deletions = 0

    for line in code_diff.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            file_path = parts[-1].lstrip("b/")
            current_file = {
                "file": file_path,
                "hunks": [],
                "additions": 0,
                "deletions": 0,
            }
            files.append(current_file)
        elif line.startswith("@@") and current_file:
            current_file["hunks"].append(line)
        elif line.startswith("+") and not line.startswith("+++") and current_file:
            current_file["additions"] += 1
            additions += 1
        elif line.startswith("-") and not line.startswith("---") and current_file:
            current_file["deletions"] += 1
            deletions += 1

    return {
        "status": "success",
        "total_files": len(files),
        "total_additions": additions,
        "total_deletions": deletions,
        "files": files,
    }


def check_python_syntax(code_snippet: str) -> dict:
    """Validate the syntax of Python code using the Python AST parser.

    Use this tool to verify whether generated Python code or an extracted
    function is syntactically valid or contains syntax errors.

    Args:
        code_snippet: Python source code string to validate.

    Returns:
        A dict with status ('valid' or 'invalid'), error message, and line number.
    """
    try:
        ast.parse(code_snippet)
        return {
            "status": "valid",
            "message": "Syntax is valid Python code.",
        }
    except SyntaxError as e:
        return {
            "status": "invalid",
            "error": str(e.msg),
            "line": e.lineno,
            "text": e.text,
        }
