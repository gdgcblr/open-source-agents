class PRAgentError(Exception):
    """Base exception for PR Reviewer Agent errors with user-friendly diagnostics."""
    def __init__(self, message: str, tip: str = None):
        super().__init__(message)
        self.message = message
        self.tip = tip

    def format_diagnostic(self) -> str:
        res = f"❌ Error: {self.message}"
        if self.tip:
            res += f"\n💡 Tip: {self.tip}"
        return res


class InvalidTargetError(PRAgentError):
    """Raised when an invalid PR URL, slug, or file target is provided."""
    pass


class GitHubFetchError(PRAgentError):
    """Raised when fetching PR or diff from GitHub fails."""
    pass


class DiffReadError(PRAgentError):
    """Raised when reading or parsing a local diff file or stdin fails."""
    pass


class ServerPortError(PRAgentError):
    """Raised when the requested web server port is already bound."""
    pass
