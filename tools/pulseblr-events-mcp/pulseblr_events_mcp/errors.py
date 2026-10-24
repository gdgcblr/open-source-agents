"""Errors safe to expose to an MCP client."""


class InputError(ValueError):
    """A request the caller can correct."""


class SourceError(RuntimeError):
    """A bounded public-source failure, without upstream secrets or response bodies."""
