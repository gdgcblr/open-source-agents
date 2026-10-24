"""One-command runner: python review.py <folder>   (see review_core/cli.py)."""

import sys

from review_core.cli import main

if __name__ == "__main__":
    sys.exit(main())
