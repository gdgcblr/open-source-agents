"""Parse a unified diff into per-file added lines with correct new-file line numbers."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class FileDiff:
    path: str
    added: list[tuple[int, str]] = field(default_factory=list)  # (new line no, text)
    patch_lines: list[str] = field(default_factory=list)
    is_new: bool = False
    deleted: bool = False

    @property
    def patch(self) -> str:
        return "\n".join(self.patch_lines)

    @property
    def added_line_numbers(self) -> set[int]:
        return {n for n, _ in self.added}

    @property
    def extension(self) -> str:
        return self.path.rsplit(".", 1)[-1].lower() if "." in self.path else ""

    @property
    def is_test(self) -> bool:
        p = self.path.lower()
        return (
            "/tests/" in f"/{p}"
            or "/test/" in f"/{p}"
            or "__tests__" in p
            or p.rsplit("/", 1)[-1].startswith("test_")
            or re.search(r"(_test\.|\.test\.|\.spec\.)", p) is not None
        )


def parse_diff(text: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    cur: FileDiff | None = None
    in_hunk = False
    new_line = 0

    for raw in text.splitlines():
        # A new file header always wins, even mid-hunk.
        if raw.startswith("diff --git "):
            cur = FileDiff(path=raw.split(" b/", 1)[-1].strip())
            files.append(cur)
            in_hunk = False
            continue
        if cur is None:
            continue

        m = HUNK_RE.match(raw)
        if m:
            in_hunk = True
            new_line = int(m.group(1))
            cur.patch_lines.append(raw)
            continue

        if not in_hunk:
            if raw.startswith("--- "):
                if raw.strip() == "--- /dev/null":
                    cur.is_new = True
            elif raw.startswith("+++ "):
                p = raw[4:].strip()
                if p == "/dev/null":
                    cur.deleted = True
                elif p.startswith("b/"):
                    cur.path = p[2:]
            continue

        # Inside a hunk
        cur.patch_lines.append(raw)
        if raw.startswith("+"):
            cur.added.append((new_line, raw[1:]))
            new_line += 1
        elif raw.startswith("-") or raw.startswith("\\"):
            pass  # removed line / "\ No newline at end of file"
        else:
            new_line += 1  # context line

    return [f for f in files if not f.deleted]
