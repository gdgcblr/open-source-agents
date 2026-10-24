"""Passphrase-protected envelope vault.

Storing seals to the vault public key (no passphrase). Retrieval needs the private key,
which is only available after unlocking with passphrase + OS-keyring pepper (Argon2id).

The whole file (entries, pending entries, failed-attempt counters, generation) is
authenticated by a state MAC keyed from the pepper, and the latest generation is also
kept in the OS keyring, so offline edits and whole-file rollback are detected. A
same-user process that can read the keyring can recompute that MAC; see README.
"""

from __future__ import annotations

import atexit
import json
import math
import os
import secrets
import sys
import tempfile
import threading
import time
import uuid
import weakref
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from . import crypto
from .crypto import DEFAULT_KDF, FORMAT, KdfParams, b64d, b64e, canonical
from .errors import (
    InsecureBackend,
    KeyguardError,
    LockedOut,
    SecretExists,
    SecretNotFound,
    SecretPending,
    TamperDetected,
    VaultExists,
    VaultIOError,
    VaultLocked,
    VaultNotFound,
    WeakPin,
    WrongPin,
)
from .redact import SecretValue, mask, valid_name

SERVICE = "d3v-keyguard"
BACKOFF_AFTER = 3
LOCKOUT_AFTER = 10
LOCK_TIMEOUT = 10.0  # seconds to wait for another process holding the vault lock
_SECURE_BACKENDS = {
    "keyring.backends.Windows",
    "keyring.backends.macOS",
    "keyring.backends.SecretService",
    "keyring.backends.libsecret",
    "keyring.backends.kwallet",
}
_CORRUPT = "vault file is corrupted or not a d3v-keyguard vault"
_OPEN_VAULTS: "weakref.WeakSet[Vault]" = weakref.WeakSet()
_COMMON = {"password", "password1", "passw0rd", "qwertyui", "qwerty123", "iloveyou", "letmein1",
           "abcdefgh", "abc12345", "admin123", "welcome1", "changeme", "qwerty", "123123", "112233",
           "121212", "123321", "abc123"}
_RUNS = ("0123456789" * 4, "abcdefghijklmnopqrstuvwxyz", "qwertyuiopasdfghjklzxcvbnm")


def default_vault_path() -> Path:
    env = os.environ.get("KEYGUARD_VAULT_PATH")
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "d3v-keyguard" / "vault.json"


def _positive(value: Any, default: float) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) and value > 0 else default


PASSPHRASE_RULE = "6+ characters (numeric PINs allowed); a longer passphrase is stronger"


def check_passphrase(pin: str) -> None:
    """Minimum 6 characters, numeric PINs allowed (product decision); rejects trivial values.

    A same-user process that copies the vault file AND the OS-keyring pepper can guess
    offline without lockout (see README threat model); longer passphrases resist that far better.
    """
    if not isinstance(pin, str) or len(pin) < 6:
        raise WeakPin(f"PIN/passphrase too short: use {PASSPHRASE_RULE}")
    low = pin.lower()
    if len(set(pin)) < 3 or low in _COMMON or any(low in run or low in run[::-1] for run in _RUNS):
        raise WeakPin("PIN/passphrase is too easy to guess (e.g. 123456, 111111, password); choose another")


_check_pin = check_passphrase  # backwards-compatible alias


def secure_keyring_backend():
    """Return the platform keyring backend, refusing insecure/plaintext ones."""
    import keyring

    backend = keyring.get_keyring()
    candidates = getattr(backend, "backends", [backend])  # unwrap ChainerBackend
    for b in candidates:
        if type(b).__module__ in _SECURE_BACKENDS:
            if type(b).__module__ == "keyring.backends.Windows":
                try:  # keep the pepper on this machine (default ENTERPRISE roams with domain profiles)
                    b.persist = "local machine"
                except Exception:
                    pass
            return b
    raise InsecureBackend(
        f"no secure OS keyring backend available (found {type(backend).__module__}); refusing to run"
    )


def _retry(fn: Callable, *args):
    """Windows: os.replace/open fail with PermissionError while another program holds the file."""
    for attempt in range(20):
        try:
            return fn(*args)
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """Exclusive cross-process lock on a sidecar file (msvcrt on Windows, flock on POSIX)."""
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as exc:
        raise VaultIOError(f"cannot open vault lock file {path}: {exc.strerror}") from None
    deadline = time.monotonic() + LOCK_TIMEOUT
    try:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise VaultIOError("vault is busy (held by another d3v-keyguard process)") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _validate(data: dict) -> None:
    """Strict schema check (after the MAC check). Raises ValueError/KeyError/TypeError."""
    if len(b64d(data["public_key"])) != 32 or not isinstance(data["wrapped"], dict):
        raise ValueError
    for slot in ("entries", "pending"):
        if not isinstance(data[slot], dict):
            raise ValueError
        for name, e in data[slot].items():
            if not valid_name(name) or not isinstance(e, dict) or not isinstance(e["box"], dict):
                raise ValueError
            if not all(isinstance(e["box"][k], str) for k in ("nonce", "ct", "epk")):
                raise ValueError
            if not isinstance(e["fp"], str) or type(e["created"]) is not int:
                raise ValueError
            if not isinstance(e["metadata"], dict) or not all(isinstance(v, str) for v in e["metadata"].values()):
                raise ValueError
            if slot == "entries" and not isinstance(e["tag"], str):
                raise ValueError
    c = data["counters"]
    if set(c) != {"failed_attempts", "last_failed_at"} or not all(type(v) is int and v >= 0 for v in c.values()):
        raise ValueError
    if type(data["generation"]) is not int or data["generation"] < 0:
        raise ValueError


class Vault:
    def __init__(
        self,
        path: str | os.PathLike | None = None,
        *,
        keyring_backend: Any = None,
        kdf_params: KdfParams | None = None,
        idle_timeout: float | None = None,
        max_session: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.path = Path(path) if path else default_vault_path()
        self._backend = keyring_backend
        # Lower-cost KDF params are only accepted via this explicit constructor argument (tests).
        self._kdf = kdf_params or DEFAULT_KDF
        self.idle_timeout = _positive(
            idle_timeout if idle_timeout is not None else os.environ.get("KEYGUARD_IDLE_TIMEOUT"), 300)
        self.max_session = _positive(
            max_session if max_session is not None else os.environ.get("KEYGUARD_MAX_SESSION"), 3600)
        self._clock = clock
        self._lock = threading.RLock()
        self._depth = 0
        self._timer: threading.Timer | None = None
        self._priv: bytearray | None = None
        self._endorse: bytearray | None = None
        self._pub: bytes | None = None
        self._session_id: str | None = None  # vault_id the session keys belong to
        self._unlocked_at = 0.0
        self._last_used = 0.0
        self.on_lock: list[Callable[[], None]] = []
        _OPEN_VAULTS.add(self)

    # ---------------------------------------------------------------- keyring
    def _keyring(self):
        if self._backend is None:
            self._backend = secure_keyring_backend()
        return self._backend

    def _kr(self, op: str, account: str, value: str | None = None):
        try:
            kr = self._keyring()
            if op == "get":
                return kr.get_password(SERVICE, account)
            if op == "set":
                return kr.set_password(SERVICE, account, value)
            return kr.delete_password(SERVICE, account)
        except KeyguardError:
            raise
        except Exception as exc:
            if op == "delete":
                return None
            raise VaultIOError(f"OS keyring error ({type(exc).__name__})") from None

    def _pepper(self, vault_id: str, create: bool = False) -> bytes:
        value = self._kr("get", f"pepper:{vault_id}")
        if value is None:
            if not create:
                raise TamperDetected("OS keyring pepper for this vault is missing")
            raw = secrets.token_bytes(32)
            self._kr("set", f"pepper:{vault_id}", b64e(raw))
            return raw
        try:
            return b64d(value)
        except ValueError:
            raise TamperDetected("OS keyring pepper for this vault is corrupted") from None

    def _current_account(self) -> str:
        """Keyring account holding the vault_id last created at this path (detects restore-after-re-init)."""
        path = os.path.normcase(os.path.abspath(self.path))
        return "current:" + crypto.digest(path.encode("utf-8"))

    # ---------------------------------------------------------------- storage
    def exists(self) -> bool:
        return self.path.exists()

    @contextmanager
    def _txn(self) -> Iterator[None]:
        """Thread lock + cross-process file lock around every read-modify-write (re-entrant)."""
        with self._lock:
            outer = self._depth == 0 and self.path.parent.is_dir()
            ctx = _file_lock(self.path.with_name(self.path.name + ".lock")) if outer else None
            if ctx:
                ctx.__enter__()
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
                if ctx:
                    ctx.__exit__(None, None, None)

    @staticmethod
    def _state_key(pepper: bytes) -> bytes:
        return crypto.hkdf(pepper, b"d3v-keyguard/2 state-mac")

    @staticmethod
    def _state_bytes(data: dict) -> bytes:
        return canonical({k: v for k, v in data.items() if k != "state_mac"})

    def _load(self) -> tuple[dict, bytes]:
        """Read, authenticate and validate the vault. Returns (data, pepper)."""
        if not self.path.exists():
            raise VaultNotFound(f"no vault at {self.path}; run 'd3v-keyguard init'")
        try:
            raw = _retry(self.path.read_bytes)
        except OSError as exc:
            raise VaultIOError(f"cannot read vault file: {exc.strerror}") from None
        try:
            data = json.loads(raw.decode("utf-8"))  # UnicodeDecodeError is a ValueError
            if data.get("format") != FORMAT:
                raise TamperDetected("unsupported or altered vault format (created by another version?)")
            vault_id = data["vault_id"]
            if not isinstance(vault_id, str):
                raise ValueError
            mac_input = self._state_bytes(data)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise TamperDetected(_CORRUPT) from None
        current = self._kr("get", self._current_account())
        if current is not None and current != vault_id:
            raise TamperDetected("this is not the vault last created at this path (an older vault restored "
                                 "after a re-init?); restored backups are refused by design, see README")
        pepper = self._pepper(vault_id)
        if not crypto.mac_ok(self._state_key(pepper), mac_input, data.get("state_mac")):
            staged = self._kr("get", f"pepper-next:{vault_id}")  # interrupted passphrase change?
            try:
                pepper = b64d(staged or "")
            except ValueError:
                pepper = b""
            if not pepper or not crypto.mac_ok(self._state_key(pepper), mac_input, data.get("state_mac")):
                raise TamperDetected("vault state MAC mismatch (file modified, rolled back or replaced)")
            self._kr("set", f"pepper:{vault_id}", staged)
            self._kr("delete", f"pepper-next:{vault_id}")
        try:
            _validate(data)
            _, params = crypto.parse_kdf(data["kdf"])
        except (ValueError, KeyError, TypeError, AttributeError):
            raise TamperDetected(_CORRUPT) from None
        if not params.at_least(self._kdf):
            raise TamperDetected("vault KDF parameters are weaker than required (possible downgrade)")
        known = self._kr("get", f"gen:{vault_id}")
        known_gen = int(known) if known and known.isdigit() else 0
        if data["generation"] < known_gen:
            raise TamperDetected("vault file is older than the last saved state (rollback detected; restored "
                                 "backups are refused by design, see README Known Limitations)")
        if data["generation"] > known_gen:
            self._kr("set", f"gen:{vault_id}", str(data["generation"]))
        return data, pepper

    def _save(self, data: dict, pepper: bytes) -> None:
        data["generation"] = data.get("generation", 0) + 1
        data["state_mac"] = crypto.mac(self._state_key(pepper), self._state_bytes(data))
        tmp = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if os.name == "posix":
                os.chmod(self.path.parent, 0o700)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".vault-", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            if os.name == "posix":
                os.chmod(tmp, 0o600)
            _retry(os.replace, tmp, self.path)
            tmp = None
        except OSError as exc:
            raise VaultIOError(f"cannot write vault file: {exc.strerror or exc}") from None
        finally:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)
        try:  # the file is the source of truth; a lagging keyring generation is re-synced on read
            self._kr("set", f"gen:{data['vault_id']}", str(data["generation"]))
        except VaultIOError:
            pass

    @staticmethod
    def _wrap_aad(data: dict) -> bytes:
        return canonical("wrap", data["format"], data["vault_id"], data["kdf"])

    @staticmethod
    def _entry_aad(data: dict, name: str, fp: str) -> bytes:
        return canonical("entry", data["format"], data["vault_id"], name, fp)

    @staticmethod
    def _endorse_bytes(data: dict, name: str, e: dict) -> bytes:
        return canonical("endorse", data["vault_id"], name, e["box"], e["fp"], e["metadata"], e["created"])

    @staticmethod
    def entry_digest(e: dict) -> str:
        """Content fingerprint of a pending entry; approval only endorses this exact content."""
        return crypto.digest(canonical("pending", e["box"], e["fp"], e["metadata"], e["created"]))

    def _wrap_keys(self, data: dict, pin: str, pepper: bytes, priv: bytes, pub: bytes, endorse: bytes) -> None:
        salt = secrets.token_bytes(16)
        data["kdf"] = {"alg": "argon2id", "salt": b64e(salt), "params": self._kdf.as_dict()}
        kek = crypto.derive_kek(pin, salt, pepper, self._kdf)
        inner = json.dumps({"priv": b64e(priv), "pub": b64e(pub), "endorse": b64e(endorse)}).encode()
        data["wrapped"] = crypto.aead_encrypt(kek, inner, self._wrap_aad(data))
        data["public_key"] = b64e(pub)

    def _seal_entry(self, data: dict, name: str, value: bytes, meta: dict, created: int,
                    pub: bytes, endorse: bytes | None) -> dict:
        fp = crypto.fingerprint(pub)
        e = {"box": crypto.seal(pub, value, self._entry_aad(data, name, fp)), "fp": fp,
             "metadata": meta, "created": created}
        if endorse is not None:
            e["tag"] = crypto.mac(endorse, self._endorse_bytes(data, name, e))
        return e

    # ------------------------------------------------------------- lifecycle
    def create(self, pin: str) -> None:
        check_passphrase(pin)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._txn():
            if self.path.exists():
                raise VaultExists(f"vault already exists at {self.path}")
            vault_id = str(uuid.uuid4())
            pepper = self._pepper(vault_id, create=True)
            priv = X25519PrivateKey.generate()
            priv_raw, pub_raw = crypto.priv_bytes(priv), crypto.pub_bytes(priv.public_key())
            endorse = secrets.token_bytes(32)
            data: dict = {"format": FORMAT, "vault_id": vault_id, "entries": {}, "pending": {},
                          "counters": {"failed_attempts": 0, "last_failed_at": 0}, "generation": 0}
            self._wrap_keys(data, pin, pepper, priv_raw, pub_raw, endorse)
            self._save(data, pepper)
            self._kr("set", self._current_account(), vault_id)
            self._set_session(priv_raw, endorse, pub_raw, vault_id)

    def _set_session(self, priv: bytes, endorse: bytes, pub: bytes, vault_id: str) -> None:
        crypto.wipe(self._priv)  # re-unlock / change-pin over an existing session
        crypto.wipe(self._endorse)
        self._priv, self._endorse, self._pub = bytearray(priv), bytearray(endorse), pub
        self._session_id = vault_id
        self._unlocked_at = self._last_used = self._clock()
        self._arm_timer()

    def _arm_timer(self) -> None:
        """Proactive auto-lock: wipe keys at the idle/max deadline even if nothing touches the vault."""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._priv is None:
            return
        now = self._clock()
        remaining = min(self.idle_timeout - (now - self._last_used), self.max_session - (now - self._unlocked_at))
        # Clamped: huge timeouts would overflow the wait; _timer_fired re-arms until the deadline.
        self._timer = threading.Timer(min(max(remaining, 0) + 0.5, threading.TIMEOUT_MAX - 1, 86400.0),
                                      self._timer_fired)
        self._timer.daemon = True
        self._timer.start()

    def _timer_fired(self) -> None:
        with self._lock:
            if self.is_unlocked():
                self._arm_timer()

    def is_unlocked(self) -> bool:
        with self._lock:
            if self._priv is None:
                return False
            now = self._clock()
            if now - self._last_used > self.idle_timeout or now - self._unlocked_at > self.max_session:
                self.lock()
                return False
            return True

    def lock(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            crypto.wipe(self._priv)
            crypto.wipe(self._endorse)
            self._priv = self._endorse = self._pub = self._session_id = None
            for cb in list(self.on_lock):
                cb()

    @staticmethod
    def _retry_after(counters: dict) -> int:
        fails = counters["failed_attempts"]
        if fails < BACKOFF_AFTER:
            return 0
        elapsed = max(0.0, time.time() - counters["last_failed_at"])
        wait = min(2 ** (fails - BACKOFF_AFTER) * 5, 900) - elapsed
        return int(wait) + 1 if wait > 0 else 0

    def unlock(self, pin: str, *, human_reset: bool = False) -> list[str]:
        """Unlock with the passphrase. Returns names of pending entries awaiting review.

        `human_reset=True` bypasses backoff/lockout. It is advisory at the API level: only the
        CLI's `reset-lockout` (interactive terminal) is meant to pass it.
        """
        with self._txn():
            data, pepper = self._load()
            c = data["counters"]
            fails = c["failed_attempts"]
            if not human_reset:
                if fails >= LOCKOUT_AFTER:
                    raise LockedOut(f"{fails} failed attempts; run 'd3v-keyguard reset-lockout' in a terminal")
                wait = self._retry_after(c)
                if wait:
                    raise LockedOut(f"too many failed attempts; retry in {wait}s")
            # Count the attempt *before* deriving: if it cannot be recorded, no guess is evaluated.
            c["failed_attempts"], c["last_failed_at"] = fails + 1, int(time.time())
            self._save(data, pepper)
            salt, params = crypto.parse_kdf(data["kdf"])
            kek = crypto.derive_kek(pin, salt, pepper, params)
            try:
                inner = json.loads(crypto.aead_decrypt(kek, data["wrapped"], self._wrap_aad(data)))
            except InvalidTag:
                raise WrongPin(f"wrong passphrase ({fails + 1} consecutive failures)") from None
            priv_raw, pinned_pub = b64d(inner["priv"]), b64d(inner["pub"])
            derived = crypto.pub_bytes(X25519PrivateKey.from_private_bytes(priv_raw).public_key())
            if derived != pinned_pub or b64d(data["public_key"]) != pinned_pub:
                raise TamperDetected("vault public key was substituted; do not store new secrets")
            c["failed_attempts"], c["last_failed_at"] = 0, 0
            self._save(data, pepper)
            self._set_session(priv_raw, b64d(inner["endorse"]), pinned_pub, data["vault_id"])
            return sorted(data["pending"])

    def change_pin(self, old_pin: str, new_pin: str) -> None:
        """Change the passphrase AND rotate everything an old copy of the file could unlock.

        A fresh pepper (so old file copies no longer verify or unwrap), a fresh X25519 key pair
        and endorsement key (so secrets stored from now on are not readable with the old
        passphrase + an old file copy), and every entry re-sealed. Old copies of the vault file
        remain decryptable with the old passphrase + old pepper for the secrets they contained.
        """
        check_passphrase(new_pin)
        with self._txn():
            self.unlock(old_pin)
            data, _ = self._load()
            old_priv = bytes(self._priv)
            priv = X25519PrivateKey.generate()
            priv_raw, pub_raw = crypto.priv_bytes(priv), crypto.pub_bytes(priv.public_key())
            endorse = secrets.token_bytes(32)
            new = dict(data, entries={}, pending={})
            for slot in ("entries", "pending"):
                for name, e in data[slot].items():
                    if slot == "entries" and self._entry_state(data, name, e) != "active":
                        raise TamperDetected(f"cannot change passphrase: {name!r} failed integrity checks; remove it first")
                    try:
                        value = crypto.unseal(old_priv, e["box"], self._entry_aad(data, name, e["fp"]))
                    except (InvalidTag, ValueError):
                        if slot == "pending":
                            continue  # undecryptable pending entry: drop it
                        raise TamperDetected(f"{name!r} failed integrity checks") from None
                    new[slot][name] = self._seal_entry(new, name, value, e["metadata"], e["created"], pub_raw,
                                                       endorse if slot == "entries" else None)
            vault_id = data["vault_id"]
            new_pepper = secrets.token_bytes(32)
            self._kr("set", f"pepper-next:{vault_id}", b64e(new_pepper))  # staged: survives a crash
            self._wrap_keys(new, new_pin, new_pepper, priv_raw, pub_raw, endorse)
            self._save(new, new_pepper)
            self._kr("set", f"pepper:{vault_id}", b64e(new_pepper))
            self._kr("delete", f"pepper-next:{vault_id}")
            self._set_session(priv_raw, endorse, pub_raw, vault_id)

    # --------------------------------------------------------------- entries
    def _session_current(self, data: dict, *, strict: bool) -> bool:
        """Is this process unlocked AND are its keys still the keys of the file on disk?

        Another process may have run change-pin (new key pair) or re-created the vault. Stale
        keys would seal new secrets to a revoked key and flag every entry as tampered, so the
        session is locked instead; with strict=True that raises VaultLocked.
        """
        if not self.is_unlocked():
            return False
        if self._session_id == data["vault_id"] and self._pub == b64d(data["public_key"]):
            return True
        self.lock()
        if strict:
            raise VaultLocked("vault keys changed in another process (change-pin or re-init); unlock again")
        return False

    def _entry_state(self, data: dict, name: str, e: dict) -> str:
        if e.get("fp") != crypto.fingerprint(b64d(data["public_key"])):
            return "tampered"
        if self._endorse is not None and not crypto.mac_ok(
            bytes(self._endorse), self._endorse_bytes(data, name, e), e.get("tag")
        ):
            return "tampered"
        return "active"

    def put(self, name: str, value: str, metadata: dict | None = None, *, overwrite: bool = False,
            captured_from: str | None = None) -> str:
        """Seal a secret. Returns 'active', or 'pending' if stored while locked.

        While locked, the value goes to a separate pending slot: an existing active secret
        with the same name stays usable until the user approves the replacement.
        The 'captured_from' metadata key is reserved for the `captured_from` keyword (ADK capture).
        """
        if not valid_name(name):
            raise ValueError("invalid secret name (use letters, digits, '_', '-', '.')")
        if not isinstance(value, str) or not value:
            raise ValueError("secret value must be a non-empty string")
        meta = {str(k)[:40]: str(v)[:200] for k, v in (metadata or {}).items() if str(k) != "captured_from"}
        if captured_from:
            meta["captured_from"] = str(captured_from)[:200]
        with self._txn():
            data, pepper = self._load()
            unlocked = self._session_current(data, strict=False)  # stale keys: stored as pending
            if not unlocked and os.environ.get("KEYGUARD_STORE_REQUIRES_UNLOCK") == "1":
                raise VaultLocked("strict mode: unlock the vault before storing secrets")
            if name in data["entries"] and not overwrite:
                raise SecretExists(f"{name!r} already exists; pass overwrite=True (CLI: --force) to replace it")
            pub = b64d(data["public_key"])  # the key on disk (equal to the session key when unlocked)
            endorse = bytes(self._endorse) if unlocked else None
            entry = self._seal_entry(data, name, value.encode("utf-8"), meta, int(time.time()), pub, endorse)
            if unlocked:
                data["entries"][name] = entry
                data["pending"].pop(name, None)
                self._last_used = self._clock()
            else:
                data["pending"][name] = entry
            self._save(data, pepper)
            return "active" if unlocked else "pending"

    def list(self) -> list[dict]:
        """Entries with status active/pending/tampered. While locked, endorsement tags cannot be
        checked, so 'active' then only means the key fingerprint matches (see status()['verified'])."""
        with self._txn():
            data, _ = self._load()
            self._session_current(data, strict=False)
            rows = []
            for n in sorted(set(data["entries"]) | set(data["pending"])):
                e = data["entries"].get(n)
                p = data["pending"].get(n)
                if e is not None:
                    row = {"name": n, "status": self._entry_state(data, n, e),
                           "metadata": e["metadata"], "created": e["created"]}
                    if p is not None:
                        row["pending_update"] = True
                else:
                    row = {"name": n, "status": "pending", "metadata": p["metadata"], "created": p["created"]}
                rows.append(row)
            return rows

    def get(self, name: str) -> SecretValue:
        with self._txn():
            if not self.is_unlocked():
                raise VaultLocked("vault is locked")
            data, _ = self._load()
            self._session_current(data, strict=True)
            e = data["entries"].get(name)
            if e is None:
                if name in data["pending"]:
                    raise SecretPending(f"{name!r} is pending approval ('d3v-keyguard approve')")
                raise SecretNotFound(f"no secret named {name!r}")
            if self._entry_state(data, name, e) != "active":
                raise TamperDetected(f"{name!r} failed integrity checks")
            try:
                value = crypto.unseal(bytes(self._priv), e["box"], self._entry_aad(data, name, e["fp"]))
            except (InvalidTag, ValueError):
                raise TamperDetected(f"{name!r} failed integrity checks") from None
            self._last_used = self._clock()
            return SecretValue(name, value.decode("utf-8"))

    def pending(self) -> list[str]:
        with self._txn():
            return sorted(self._load()[0]["pending"])

    def review_items(self) -> list[dict]:
        """Pending entries with what the user needs to decide (requires unlock; previews are masked)."""
        with self._txn():
            if not self.is_unlocked():
                raise VaultLocked("vault is locked")
            data, _ = self._load()
            self._session_current(data, strict=True)
            items = []
            for n, e in sorted(data["pending"].items()):
                same = None  # for replacements: is the new value identical to the active one?
                try:
                    if e["fp"] != crypto.fingerprint(self._pub):
                        raise ValueError
                    value = crypto.unseal(bytes(self._priv), e["box"], self._entry_aad(data, n, e["fp"]))
                    preview, valid = mask(value.decode("utf-8")), True
                    cur = data["entries"].get(n)
                    if cur is not None and self._entry_state(data, n, cur) == "active":
                        old = crypto.unseal(bytes(self._priv), cur["box"], self._entry_aad(data, n, cur["fp"]))
                        same = secrets.compare_digest(value, old)
                except (InvalidTag, ValueError):
                    preview, valid = "[cannot be decrypted - tampered]", False
                items.append({"name": n, "digest": self.entry_digest(e), "created": e["created"],
                              "metadata": dict(e["metadata"]), "replaces": n in data["entries"],
                              "same_as_current": same, "preview": preview, "valid": valid})
            return items

    def approve(self, selection: dict[str, str]) -> list[str]:
        """Endorse pending entries {name: digest from review_items()} (requires unlock).

        An entry is approved only if its content still matches the digest the user reviewed.
        """
        with self._txn():
            if not self.is_unlocked():
                raise VaultLocked("vault is locked")
            data, pepper = self._load()
            self._session_current(data, strict=True)
            done = []
            for n, want in selection.items():
                e = data["pending"].get(n)
                if e is None or self.entry_digest(e) != want or e["fp"] != crypto.fingerprint(self._pub):
                    continue
                try:
                    crypto.unseal(bytes(self._priv), e["box"], self._entry_aad(data, n, e["fp"]))
                except (InvalidTag, ValueError):
                    continue
                e["tag"] = crypto.mac(bytes(self._endorse), self._endorse_bytes(data, n, e))
                data["entries"][n] = data["pending"].pop(n)
                done.append(n)
            if done:
                self._save(data, pepper)
            return done

    def reject(self, names: list[str]) -> list[str]:
        """Discard pending entries (active secrets with the same name are kept)."""
        with self._txn():
            data, pepper = self._load()
            done = [n for n in names if data["pending"].pop(n, None) is not None]
            if done:
                self._save(data, pepper)
            return done

    def delete(self, name: str) -> bool:
        with self._txn():
            data, pepper = self._load()
            found = data["entries"].pop(name, None) is not None
            found = data["pending"].pop(name, None) is not None or found
            if found:
                self._save(data, pepper)
            return found

    def status(self) -> dict:
        with self._txn():
            if not self.path.exists():
                return {"initialized": False, "unlocked": False, "path": str(self.path)}
            data, _ = self._load()
            unlocked = self._session_current(data, strict=False)
            states = [self._entry_state(data, n, e) for n, e in data["entries"].items()]
            c = data["counters"]
            return {
                "initialized": True,
                "unlocked": unlocked,
                "path": str(self.path),
                "secrets": len(states),
                "pending": len(data["pending"]),
                "tampered": states.count("tampered"),
                # Endorsement tags can only be checked with the unlocked key: while locked,
                # 'tampered' counts key-fingerprint mismatches only.
                "verified": unlocked,
                "failed_attempts": c["failed_attempts"],
                "locked_out": c["failed_attempts"] >= LOCKOUT_AFTER,
                "retry_after": self._retry_after(c),
            }


@atexit.register
def _lock_all() -> None:
    for v in list(_OPEN_VAULTS):
        try:
            v.lock()
        except Exception:
            pass
