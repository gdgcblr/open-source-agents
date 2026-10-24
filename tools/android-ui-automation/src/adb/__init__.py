"""ADB access layer."""

from .client import ADBClient, CommandResult, classify_error

__all__ = ["ADBClient", "CommandResult", "classify_error"]
