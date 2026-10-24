class LedgerError(Exception):
    """A rejected request. `code` is stable and meant for agents and tests."""

    def __init__(self, code: str, message: str, **details):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details

    def to_dict(self) -> dict:
        return {"ok": False, "error_code": self.code, "message": self.message, **self.details}
