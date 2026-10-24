#!/usr/bin/env python3
"""Reset and seed fictional demo community data."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rentrakshak.services.demo_seed import seed_demo


def main() -> None:
    db = seed_demo()
    print(f"Seeded demo data at {db}")


if __name__ == "__main__":
    main()
