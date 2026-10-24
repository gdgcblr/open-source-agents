"""Unified Git diff parser."""

import re
from pathlib import Path
from typing import List, Dict, Optional, Set
from .models import FileDiff, DiffHunk

HUNK_HEADER_PATTERN = re.compile(
    r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)$"
)


class DiffParser:
    """Parses unified diff text into structured FileDiff and DiffHunk models."""

    @staticmethod
    def parse(diff_text: str) -> List[FileDiff]:
        """Parses unified git diff content into a list of FileDiff objects."""
        files: List[FileDiff] = []
        current_file: Optional[FileDiff] = None
        current_hunk: Optional[DiffHunk] = None
        current_new_line = 0

        lines = diff_text.splitlines()

        for line in lines:
            # Check for file headers
            if line.startswith("--- "):
                old_path = DiffParser._clean_path(line[4:].strip())
                # Create a placeholder if not already created
                if current_file is None or current_file.old_path != old_path:
                    current_file = FileDiff(old_path=old_path, new_path="")
            elif line.startswith("+++ "):
                new_path = DiffParser._clean_path(line[4:].strip())
                if current_file is not None:
                    current_file.new_path = new_path
                    files.append(current_file)
                else:
                    current_file = FileDiff(old_path=new_path, new_path=new_path)
                    files.append(current_file)
            elif line.startswith("diff --git "):
                # Start of a new diff block
                current_file = None
                current_hunk = None
            elif line.startswith("@@"):
                match = HUNK_HEADER_PATTERN.match(line)
                if match and current_file is not None:
                    old_start = int(match.group(1))
                    old_count = int(match.group(2)) if match.group(2) is not None else 1
                    new_start = int(match.group(3))
                    new_count = int(match.group(4)) if match.group(4) is not None else 1
                    header = match.group(5).strip()

                    current_hunk = DiffHunk(
                        old_start=old_start,
                        old_count=old_count,
                        new_start=new_start,
                        new_count=new_count,
                        header=header,
                        modified_new_lines=set(),
                        lines=[]
                    )
                    current_file.hunks.append(current_hunk)
                    current_new_line = new_start
            elif current_hunk is not None:
                current_hunk.lines.append(line)
                if line.startswith("+") and not line.startswith("+++"):
                    current_hunk.modified_new_lines.add(current_new_line)
                    current_new_line += 1
                elif line.startswith("-") and not line.startswith("---"):
                    # Deletion line does not advance new file line counter,
                    # but mark the anchor line in the new file as affected
                    current_hunk.modified_new_lines.add(max(1, current_new_line))
                elif line.startswith(" "):
                    current_new_line += 1

        # Fallback if hunks exist without modifications marked
        for f in files:
            for h in f.hunks:
                if not h.modified_new_lines and h.new_count > 0:
                    for l_idx in range(h.new_start, h.new_start + h.new_count):
                        h.modified_new_lines.add(l_idx)

        return files

    @staticmethod
    def _clean_path(raw_path: str) -> str:
        """Strips a/ and b/ git prefixes and whitespace."""
        p = raw_path.strip()
        if p.startswith("a/") or p.startswith("b/"):
            p = p[2:]
        elif p.startswith('"') and p.endswith('"'):
            p = p[1:-1]
        return p

