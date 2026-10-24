"""Parser for unified git diffs."""

from __future__ import annotations
import re
from dataclasses import dataclass, field


@dataclass
class DiffLine:
    line_type: str  # '+', '-', ' '
    content: str
    new_line_no: int | None = None
    old_line_no: int | None = None


@dataclass
class FileDiff:
    old_path: str
    new_path: str
    is_new: bool = False
    is_deleted: bool = False
    is_binary: bool = False
    lines: list[DiffLine] = field(default_factory=list)
    raw_patch: str = ""

    @property
    def filename(self) -> str:
        if self.new_path and self.new_path != "/dev/null":
            return self.new_path
        return self.old_path

    def added_lines(self) -> list[tuple[int, str]]:
        """Return list of (line_number, content) for added lines."""
        return [
            (line.new_line_no, line.content)
            for line in self.lines
            if line.line_type == "+" and line.new_line_no is not None
        ]


def parse_unified_diff(diff_text: str) -> list[FileDiff]:
    """Parse standard unified diff text into structured FileDiff objects."""
    files: list[FileDiff] = []
    if not diff_text or not diff_text.strip():
        return files

    raw_file_blocks = re.split(r"(?=diff --git )", diff_text)

    for block in raw_file_blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.splitlines()
        old_path = ""
        new_path = ""
        is_new = False
        is_deleted = False
        is_binary = "Binary files" in block

        diff_header = lines[0] if lines else ""
        header_match = re.match(r"diff --git a/(.*) b/(.*)", diff_header)
        if header_match:
            old_path = header_match.group(1)
            new_path = header_match.group(2)

        file_diff_lines: list[DiffLine] = []
        new_line_cursor = 0
        old_line_cursor = 0

        for line in lines:
            if line.startswith("new file mode"):
                is_new = True
            elif line.startswith("deleted file mode"):
                is_deleted = True
            elif line.startswith("--- a/"):
                old_path = line[6:]
            elif line.startswith("+++ b/"):
                new_path = line[6:]
            elif line.startswith("@@"):
                # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
                hunk_match = re.search(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
                if hunk_match:
                    old_line_cursor = int(hunk_match.group(1))
                    new_line_cursor = int(hunk_match.group(2))
            elif line.startswith("+") and not line.startswith("+++"):
                file_diff_lines.append(
                    DiffLine(
                        line_type="+",
                        content=line[1:],
                        new_line_no=new_line_cursor,
                        old_line_no=None,
                    )
                )
                new_line_cursor += 1
            elif line.startswith("-") and not line.startswith("---"):
                file_diff_lines.append(
                    DiffLine(
                        line_type="-",
                        content=line[1:],
                        new_line_no=None,
                        old_line_no=old_line_cursor,
                    )
                )
                old_line_cursor += 1
            elif line.startswith(" "):
                file_diff_lines.append(
                    DiffLine(
                        line_type=" ",
                        content=line[1:],
                        new_line_no=new_line_cursor,
                        old_line_no=old_line_cursor,
                    )
                )
                new_line_cursor += 1
                old_line_cursor += 1

        if not old_path and not new_path:
            # Fallback for simple diffs without 'diff --git'
            first_plus = next((l for l in lines if l.startswith("+++ ")), None)
            if first_plus:
                new_path = first_plus.replace("+++ ", "").replace("b/", "").strip()
                old_path = new_path

        if old_path or new_path:
            files.append(
                FileDiff(
                    old_path=old_path,
                    new_path=new_path,
                    is_new=is_new,
                    is_deleted=is_deleted,
                    is_binary=is_binary,
                    lines=file_diff_lines,
                    raw_patch=block,
                )
            )

    return files
