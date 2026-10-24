"""Exception types. Anything derived from UsageError maps to CLI exit code 2."""


class UsageError(Exception):
    """Base class for errors caused by bad input or a refused operation."""


class FixtureError(UsageError):
    """The fixture file is malformed or violates a hard limit."""


class PolicyViolation(UsageError):
    """A guardrail refused to let the requested operation happen."""
