#!/usr/bin/env python3
"""Deterministic safety report CLI (no API key required)."""

from __future__ import annotations

import argparse
import json
import sys

from rentrakshak.db.database import init_db
from rentrakshak.services.safety_report import generate_rental_safety_report


def main() -> int:
    parser = argparse.ArgumentParser(description="RentRakshak deterministic safety report")
    parser.add_argument("--listing", required=True, help="Listing text or path with @prefix")
    parser.add_argument("--chat", default="", help="Optional chat transcript")
    parser.add_argument("--locality", default="", help="Locality hint")
    args = parser.parse_args()

    listing = args.listing
    if listing.startswith("@"):
        listing = open(listing[1:], encoding="utf-8").read()

    init_db()
    report = generate_rental_safety_report(
        listing,
        args.chat or None,
        locality_hint=args.locality or None,
    )
    json.dump(report.model_dump(), sys.stdout, indent=2, default=str)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
