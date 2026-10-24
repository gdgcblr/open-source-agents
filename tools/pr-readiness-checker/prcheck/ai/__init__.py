"""Optional AI review. Advisory only: it never changes pass/fail or the exit code."""

from .review import review_readme

__all__ = ["review_readme"]
