"""Exception hierarchy. Messages never contain secret values or PINs."""


class KeyguardError(Exception):
    """Base error for d3v-keyguard."""


class VaultNotFound(KeyguardError):
    pass


class VaultExists(KeyguardError):
    pass


class VaultLocked(KeyguardError):
    pass


class VaultIOError(KeyguardError):
    """The vault file or OS keyring could not be read/written (busy, permissions, ...)."""


class WrongPin(KeyguardError):
    pass


class WeakPin(KeyguardError, ValueError):
    """The chosen passphrase is too weak to resist offline guessing."""


class LockedOut(KeyguardError):
    pass


class TamperDetected(KeyguardError):
    pass


class SecretNotFound(KeyguardError):
    pass


class SecretExists(KeyguardError):
    """An active secret with this name exists; pass overwrite=True / --force to replace it."""


class SecretPending(KeyguardError):
    pass


class PolicyDenied(KeyguardError):
    pass


class InsecureBackend(KeyguardError):
    pass


class PromptCancelled(KeyguardError):
    """The user cancelled (or did not answer) a secure prompt."""


class PromptUnavailable(PromptCancelled):
    """No secure prompt could be shown (no GUI / helper failed). Callers may fall back."""
