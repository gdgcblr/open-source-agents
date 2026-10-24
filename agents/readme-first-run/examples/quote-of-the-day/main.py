"""Prints a programming quote for a given day of the year."""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

from colorama import Fore, Style
from dotenv import load_dotenv

QUOTES_FILE = Path(__file__).with_name("quotes.json")


def pick_quote(quotes, day):
    return quotes[(day - 1) % len(quotes)]


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Print a quote of the day.")
    parser.add_argument("--day", type=int, help="day number to use (default: today's day of the year)")
    args = parser.parse_args()

    category = os.getenv("QUOTE_CATEGORY", "engineering")
    quotes = json.loads(QUOTES_FILE.read_text(encoding="utf-8"))
    if category not in quotes:
        sys.exit(f"Unknown QUOTE_CATEGORY {category!r}, pick one of: {', '.join(sorted(quotes))}")

    day = args.day or datetime.date.today().timetuple().tm_yday
    quote = pick_quote(quotes[category], day)

    title = f"Quote of the day #{day} ({category})"
    # colors only when printing to a real terminal
    if sys.stdout.isatty():
        title = Style.BRIGHT + Fore.CYAN + title + Style.RESET_ALL
    print(title)
    print(f'"{quote["text"]}"')
    print(f"  - {quote['author']}")


if __name__ == "__main__":
    main()
