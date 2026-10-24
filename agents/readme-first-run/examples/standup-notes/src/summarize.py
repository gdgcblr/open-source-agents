"""Turns a plain notes file into standup bullets."""

import sys
from pathlib import Path

SECTIONS = {"done": "Yesterday", "doing": "Today", "blocked": "Blockers"}


def parse(lines):
    grouped = {key: [] for key in SECTIONS}
    skipped = 0
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        prefix, sep, rest = line.partition(":")
        key = prefix.strip().lower()
        if sep and key in grouped and rest.strip():
            grouped[key].append(rest.strip())
        else:
            skipped += 1
    return grouped, skipped


def render(name, grouped, skipped):
    out = [f"Standup for {name}", ""]
    for key, title in SECTIONS.items():
        out.append(title)
        out.extend(f"  - {item}" for item in grouped[key] or ["nothing"])
    if skipped:
        word = "line" if skipped == 1 else "lines"
        out += ["", f"{skipped} {word} skipped (no done/doing/blocked prefix)"]
    return "\n".join(out)


def main(argv):
    if len(argv) != 2:
        sys.exit(f"usage: {Path(argv[0]).name} NOTES_FILE")
    notes = Path(argv[1])
    if not notes.is_file():
        sys.exit(f"error: notes file not found: {notes}")
    grouped, skipped = parse(notes.read_text(encoding="utf-8").splitlines())
    print(render(argv[1], grouped, skipped))


if __name__ == "__main__":
    main(sys.argv)
