"""Tiny intentionally buggy config parser used by the reproducible example."""

def parse_timeout(value: int | None, default: int = 30) -> int:
    """Return a configured timeout, falling back when no value was provided."""
    # Bug: zero is falsey, so the fallback overwrites an explicit user value.
    return value or default
