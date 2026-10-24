"""Terminal stand-in for the glasses lens: step through a deck like the Neural Band.

Keys: Enter / Space / → / n = next, ← / p / b = back, q = quit.

Example:
    python glasses_preview.py out/deck.json
    python glasses_preview.py out/deck.json --print   # all cards, no key presses
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

LENS_TEXT_WIDTH = 30


@dataclass(frozen=True)
class Card:
    header: str
    body: str
    footer: str


def _header(heading: str, counter: str) -> str:
    """Heading plus counter in one lens line; the heading is shortened, never the counter."""
    room = LENS_TEXT_WIDTH - len(counter) - 2
    if len(heading) > room:
        heading = heading[: max(room - 1, 0)].rstrip() + "…"
    return f"{heading}  {counter}"


def load_cards(deck: dict) -> list[Card]:
    cues = deck.get("cues", [])
    total = len(cues)
    cards = [
        Card(
            header=_header(cue["heading"], f"{cue['index'] + 1}/{total}"),
            body=cue["text"],
            footer=f"say by {cue['sayByLabel']}" + ("  ⚠" if cue.get("flags") else ""),
        )
        for cue in cues
    ]
    qa = deck.get("qa", [])
    cards += [
        Card(
            header=_header("Q&A", f"{i}/{len(qa)}"),
            body=f"Q: {item['question']}",
            footer=item["answer"],
        )
        for i, item in enumerate(qa, start=1)
    ]
    return cards


def render(card: Card) -> str:
    inner = LENS_TEXT_WIDTH + 2
    lines = [card.header, ""]
    lines += textwrap.wrap(card.body, LENS_TEXT_WIDTH) or [""]
    lines += [""] + textwrap.wrap(card.footer, LENS_TEXT_WIDTH)
    rows = [f"│ {line:<{LENS_TEXT_WIDTH}} │" for line in lines]
    return "\n".join([f"╭{'─' * inner}╮", *rows, f"╰{'─' * inner}╯"])


def _read_key() -> str:
    """One key press on macOS/Linux terminals; falls back to a line of input."""
    try:
        import termios
        import tty
    except ImportError:
        return input("[Enter = next, b = back, q = quit] ").strip().lower() or "n"
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        key = sys.stdin.read(1)
        if key == "\x1b":
            key += sys.stdin.read(2)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return {"\r": "n", " ": "n", "\x1b[C": "n", "\x1b[D": "b", "p": "b", "\x03": "q"}.get(key, key)


def present(cards: list[Card]) -> None:
    i = 0
    while True:
        print("\033[2J\033[H" + render(cards[i]))
        print("\nEnter/→ next · ← back · q quit")
        key = _read_key()
        if key == "q":
            return
        if key == "n":
            if i == len(cards) - 1:
                return
            i += 1
        elif key == "b":
            i = max(0, i - 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("deck", nargs="?", default="out/deck.json", help="Path to deck.json.")
    parser.add_argument("--print", action="store_true", help="Print every card and exit.")
    args = parser.parse_args(argv)

    try:
        deck = json.loads(Path(args.deck).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: could not read {args.deck}: {exc}", file=sys.stderr)
        return 2
    cards = load_cards(deck)
    if not cards:
        print("Error: the deck has no cues.", file=sys.stderr)
        return 2

    if args.print or not sys.stdin.isatty():
        print("\n\n".join(render(card) for card in cards))
    else:
        present(cards)
    return 0


if __name__ == "__main__":
    sys.exit(main())
