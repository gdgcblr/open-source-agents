"""Unified-diff parser.

Pure, stdlib-only functions that turn ``git diff`` text into a small,
testable data structure. No file, git, or network I/O happens here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

# Change types a single file can have in a diff.
ADDED = "added"
DELETED = "deleted"
MODIFIED = "modified"
RENAMED = "renamed"


@dataclass
class FileChange:
    """A single file's worth of change extracted from a diff."""

    path: str
    change_type: str
    added: int = 0
    removed: int = 0

    @property
    def ext(self) -> str:
        """Lower-cased file extension including the dot (``""`` if none)."""
        return os.path.splitext(self.path)[1].lower()


@dataclass
class DiffSummary:
    """Aggregated view of every file changed in a diff."""

    files: List[FileChange] = field(default_factory=list)

    @property
    def total_added(self) -> int:
        return sum(f.added for f in self.files)

    @property
    def total_removed(self) -> int:
        return sum(f.removed for f in self.files)

    @property
    def file_count(self) -> int:
        return len(self.files)

    def is_empty(self) -> bool:
        return not self.files


def _strip_ab_prefix(path: str) -> str:
    """Drop the leading ``a/`` or ``b/`` that git prepends to diff paths."""
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def parse_diff(text: str) -> DiffSummary:
    """Parse unified diff ``text`` into a :class:`DiffSummary`.

    Understands the ``diff --git`` block header, ``new file mode`` /
    ``deleted file mode`` / ``rename from|to`` metadata, and counts added
    (``+``) and removed (``-``) lines while ignoring the ``+++`` / ``---``
    file header lines. Anything it does not recognise is simply skipped,
    so malformed input yields an empty-ish summary rather than raising.
    """
    summary = DiffSummary()
    current: FileChange | None = None

    def flush() -> None:
        if current is not None:
            summary.files.append(current)

    for line in text.splitlines():
        if line.startswith("diff --git "):
            # Start of a new file block; commit the previous one first.
            flush()
            # "diff --git a/path b/path" -> default to the b/ path.
            parts = line.split()
            path = _strip_ab_prefix(parts[-1]) if len(parts) >= 4 else "unknown"
            current = FileChange(path=path, change_type=MODIFIED)
            continue

        if current is None:
            # Lines before the first "diff --git" header are ignored.
            continue

        if line.startswith("new file mode"):
            current.change_type = ADDED
        elif line.startswith("deleted file mode"):
            current.change_type = DELETED
        elif line.startswith("rename from "):
            current.change_type = RENAMED
        elif line.startswith("rename to "):
            current.change_type = RENAMED
            current.path = _strip_ab_prefix(line[len("rename to "):].strip())
        elif line.startswith("+++ "):
            # File header, not a content line: capture path, don't count.
            raw = line[4:].strip()
            if raw not in ("/dev/null", ""):
                current.path = _strip_ab_prefix(raw)
        elif line.startswith("--- "):
            # File header for the "before" side; never counted.
            continue
        elif line.startswith("+"):
            current.added += 1
        elif line.startswith("-"):
            current.removed += 1
        # "@@", "index ", context lines, etc. carry no count signal.

    flush()
    return summary
