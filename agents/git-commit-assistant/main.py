"""Entry point for git-commit-assistant.

Run with ``python main.py`` from this directory. All behaviour lives in
``commit_assistant.cli`` so the logic stays importable and unit-testable.
"""

from commit_assistant.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
