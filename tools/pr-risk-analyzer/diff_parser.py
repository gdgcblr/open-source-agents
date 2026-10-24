import re
from pathlib import PurePosixPath

from models import DiffLine, FileChange


HUNK_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
)


def _clean_path(raw_path: str) -> str | None:
    """Normalize a Git diff path; /dev/null represents a missing file."""
    raw_path = raw_path.strip()

    if raw_path == "/dev/null":
        return None

    # Git normally prefixes paths with a/ and b/.
    if raw_path.startswith(("a/", "b/")):
        raw_path = raw_path[2:]

    return str(PurePosixPath(raw_path))


def parse_unified_diff(diff_text: str) -> list[FileChange]:
    """Parse unified diff text into file changes and line records."""
    files: list[FileChange] = []
    current: FileChange | None = None

    old_line: int | None = None
    new_line: int | None = None
    in_hunk = False

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            current = FileChange(old_path=None, new_path=None)
            files.append(current)
            old_line = new_line = None
            in_hunk = False
            continue

        if current is None:
            continue

        if line.startswith("Binary files ") or line.startswith("GIT binary patch"):
            current.is_binary = True
            in_hunk = False
            continue

        if line.startswith("--- "):
            current.old_path = _clean_path(line[4:].split("\t", 1)[0])
            continue

        if line.startswith("+++ "):
            current.new_path = _clean_path(line[4:].split("\t", 1)[0])

            if current.old_path is None:
                current.status = "added"
            elif current.new_path is None:
                current.status = "deleted"
            elif current.old_path != current.new_path:
                current.status = "renamed"
            continue

        hunk = HUNK_RE.match(line)
        if hunk:
            old_line = int(hunk.group(1))
            new_line = int(hunk.group(3))
            in_hunk = True
            continue

        if line.startswith("rename from "):
            current.old_path = _clean_path(line[len("rename from "):])
            current.status = "renamed"
            continue

        if line.startswith("rename to "):
            current.new_path = _clean_path(line[len("rename to "):])
            current.status = "renamed"
            continue

        if not in_hunk:
            # File metadata, rename headers, index lines, and other headers.
            continue

        if line.startswith("\\ No newline at end of file"):
            continue

        if line.startswith("+"):
            current.lines.append(
                DiffLine(
                    kind="added",
                    content=line[1:],
                    new_line_number=new_line,
                )
            )
            if new_line is not None:
                new_line += 1

        elif line.startswith("-"):
            current.lines.append(
                DiffLine(
                    kind="deleted",
                    content=line[1:],
                    old_line_number=old_line,
                )
            )
            if old_line is not None:
                old_line += 1

        elif line.startswith(" "):
            current.lines.append(
                DiffLine(
                    kind="context",
                    content=line[1:],
                    old_line_number=old_line,
                    new_line_number=new_line,
                )
            )
            if old_line is not None:
                old_line += 1
            if new_line is not None:
                new_line += 1

        else:
            # Unexpected content means we should not parse it as source.
            in_hunk = False

    # A final status fallback for valid but incomplete diff headers.
    for file_change in files:
        if file_change.status == "modified":
            if file_change.old_path is None and file_change.new_path:
                file_change.status = "added"
            elif file_change.new_path is None and file_change.old_path:
                file_change.status = "deleted"
            elif (
                file_change.old_path
                and file_change.new_path
                and file_change.old_path != file_change.new_path
            ):
                file_change.status = "renamed"

    return files