"""Git diff analyzer to isolate newly added lines from legacy code."""
from __future__ import annotations

import re
import subprocess
from typing import Dict, Set


class DiffAnalyzer:
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path

    def get_diff_lines(self, base_ref: str = "origin/main") -> Dict[str, Set[int]]:
        """
        Parses unified diff to find added/modified lines per file.
        Returns: { 'path/to/file.py': {14, 15, 16, 22} }
        """
        cmd = ["git", "-C", self.repo_path, "diff", "-U0", f"{base_ref}...HEAD"]
        try:
            raw_diff = subprocess.check_output(cmd, stderr=subprocess.PIPE, text=True)
        except Exception:
            try:
                # Fallback to working copy diff if base_ref does not exist
                raw_diff = subprocess.check_output(
                    ["git", "-C", self.repo_path, "diff", "-U0", "HEAD"],
                    stderr=subprocess.PIPE,
                    text=True
                )
            except Exception:
                raw_diff = ""

        return self.parse_unified_diff(raw_diff)

    def parse_unified_diff(self, diff_text: str) -> Dict[str, Set[int]]:
        added_lines: Dict[str, Set[int]] = {}
        current_file: str | None = None
        hunk_header_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

        for line in diff_text.splitlines():
            if line.startswith("+++ b/"):
                current_file = line[6:].strip()
                if current_file not in added_lines:
                    added_lines[current_file] = set()
            elif line.startswith("@@ ") and current_file:
                match = hunk_header_re.match(line)
                if match:
                    start_line = int(match.group(1))
                    count = int(match.group(2)) if match.group(2) else 1
                    for offset in range(count):
                        added_lines[current_file].add(start_line + offset)

        return added_lines

    def is_line_in_diff(self, file_path: str, line_no: int, diff_map: Dict[str, Set[int]]) -> bool:
        normalized_path = file_path.lstrip("./")
        return line_no in diff_map.get(normalized_path, set())
