"""Local Git capture, template selection, and input validation.

The public dataclasses and limits below are the contract shared by the CLI,
agent tools, and output checks.
"""

from __future__ import annotations

import hashlib
import os
import re
import selectors
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

MAX_CHANGED_PATHS = 20
MAX_RAW_METADATA_BYTES = 32_768
MAX_DIFF_BYTES = 65_536
MAX_TEMPLATE_BYTES = 16_384
MAX_INTENT_BYTES = 2_048
GIT_TIMEOUT_SECONDS = 5

FALLBACK_TEMPLATE = "## Summary\n\n## Why\n\n## Testing\n\n## Suggested checks\n"

_GIT = "git"
_CLEARED_GIT_VARIABLES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_EXTERNAL_DIFF",
)
_TEMPLATE_CANDIDATES = (
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/pull_request_template.md",
    "PULL_REQUEST_TEMPLATE.md",
    "pull_request_template.md",
)
_RAW_DIFF_ARGUMENTS = (
    "diff",
    "--cached",
    "--raw",
    "-z",
    "--no-abbrev",
    "--no-renames",
    "--no-color",
    "--no-ext-diff",
    "--no-textconv",
    "--ignore-submodules=none",
    "--",
)
_PATCH_DIFF_ARGUMENTS = (
    "diff",
    "--cached",
    "--no-renames",
    "--no-color",
    "--no-ext-diff",
    "--no-textconv",
    "--unified=3",
    "--ignore-submodules=none",
    "--src-prefix=a/",
    "--dst-prefix=b/",
    "--",
)
_ALLOWED_MODES = frozenset({"000000", "100644", "100755"})
_REGULAR_MODES = frozenset({"100644", "100755"})
_ALLOWED_STATUSES = frozenset({"A", "D", "M"})
_UNMERGED_STATUSES = frozenset({"U", "AA", "DD", "AU", "UA", "DU", "UD", "UU"})
_CREDENTIAL_PLACEHOLDERS = frozenset(
    {
        "your_api_key_here",
        "your_token_here",
        "your_password_here",
        "replace_me",
        "example",
    }
)
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"
)
_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"""
    (?<![A-Za-z0-9_])
    [\"']?
    (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    [\"']?
    [\t ]*[:=][\t ]*
    """,
    re.IGNORECASE | re.VERBOSE,
)
_CREDENTIAL_VALUE_RE = re.compile(
    r"""
    (
        "(?:\\.|[^"\\])*"
        |'(?:\\.|[^'\\])*'
        |[^\s,;#}\]]+
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
_TOKEN_RE = re.compile(r"(?:ghp_|github_pat_|sk-)[A-Za-z0-9_-]{20,}")
_BINARY_MARKER_RE = re.compile(
    rb"(?m)^(?:Binary files .* differ|GIT binary patch)\r?$"
)
_INVALID_REPOSITORY = (
    "The selected repository path is not a readable, non-bare Git working tree."
)


@dataclass(frozen=True)
class ChangedFile:
    """One staged path from Git's NUL-delimited raw metadata."""

    path: str
    old_mode: str
    new_mode: str
    status: str


@dataclass(frozen=True)
class RepositorySnapshot:
    """The immutable, validated evidence used for one generation run."""

    root: Path
    files: tuple[ChangedFile, ...]
    diff: str
    diff_sha256: str
    template: str
    template_source: str | None


class InputError(Exception):
    """An expected local failure with a stable code and safe message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def capture_snapshot(repo: Path) -> RepositorySnapshot:
    """Capture and validate staged changes from one Git working tree."""
    requested = Path(repo)
    try:
        info = requested.stat()
    except OSError:
        raise InputError("INVALID_REPOSITORY", _INVALID_REPOSITORY) from None
    if not stat.S_ISDIR(info.st_mode):
        raise InputError("INVALID_REPOSITORY", _INVALID_REPOSITORY)

    try:
        start = requested.resolve(strict=True)
    except (OSError, RuntimeError):
        raise InputError("INVALID_REPOSITORY", _INVALID_REPOSITORY) from None

    try:
        root_output = _run_git(
            [_GIT, "rev-parse", "--show-toplevel"],
            start,
            MAX_RAW_METADATA_BYTES,
            "resolving the repository root",
        )
    except InputError as error:
        if error.code in {"GIT_TIMEOUT", "INPUT_TOO_LARGE"}:
            raise
        raise InputError("INVALID_REPOSITORY", _INVALID_REPOSITORY) from None

    try:
        root_text = root_output.decode("utf-8")
    except UnicodeDecodeError:
        raise InputError("INVALID_REPOSITORY", _INVALID_REPOSITORY) from None
    root_text = root_text.removesuffix("\n")
    if not root_text:
        raise InputError("INVALID_REPOSITORY", _INVALID_REPOSITORY)

    try:
        root = Path(root_text).resolve(strict=True)
    except (OSError, RuntimeError):
        raise InputError("INVALID_REPOSITORY", _INVALID_REPOSITORY) from None
    if not root.is_dir() or not _is_within(start, root):
        raise InputError("INVALID_REPOSITORY", _INVALID_REPOSITORY)

    raw_metadata = _run_git(
        [_GIT, *_RAW_DIFF_ARGUMENTS],
        root,
        MAX_RAW_METADATA_BYTES,
        "reading staged metadata",
    )
    if not raw_metadata:
        raise InputError(
            "NO_STAGED_CHANGES",
            "No staged changes were found. Select and stage the files to describe.",
        )
    files = _parse_raw_metadata(raw_metadata)

    patch = _run_git(
        [_GIT, *_PATCH_DIFF_ARGUMENTS],
        root,
        MAX_DIFF_BYTES,
        "reading the staged diff",
    )
    raw_metadata_after = _run_git(
        [_GIT, *_RAW_DIFF_ARGUMENTS],
        root,
        MAX_RAW_METADATA_BYTES,
        "rechecking staged metadata",
    )
    if raw_metadata_after != raw_metadata:
        raise InputError(
            "INDEX_CHANGED",
            "The Git index changed during capture. Leave the index unchanged and run again.",
        )

    if _has_binary_marker(patch):
        raise InputError(
            "UNSUPPORTED_CHANGE",
            "Staged changes include binary content. Only text changes are supported.",
        )
    try:
        diff = patch.decode("utf-8")
    except UnicodeDecodeError:
        raise InputError(
            "INVALID_ENCODING", "The staged diff is not valid UTF-8."
        ) from None

    if _has_sensitive_content(diff):
        raise InputError(
            "SENSITIVE_INPUT",
            "The staged diff contains recognizable credential material. "
            "Remove it before requesting a draft.",
        )

    template, template_source = _load_template(root)
    if template_source is not None and _has_sensitive_content(template):
        raise InputError(
            "SENSITIVE_INPUT",
            f"PR template {template_source!r} contains recognizable credential "
            "material. Remove it before requesting a draft.",
        )

    return RepositorySnapshot(
        root=root,
        files=files,
        diff=diff,
        diff_sha256=hashlib.sha256(patch).hexdigest(),
        template=template,
        template_source=template_source,
    )


def _is_within(path: Path, root: Path) -> bool:
    """Return whether ``path`` is ``root`` or below it, including case aliases."""
    if path == root or root in path.parents:
        return True
    current = path
    while True:
        try:
            if os.path.samefile(current, root):
                return True
        except OSError:
            return False
        parent = current.parent
        if parent == current:
            return False
        current = parent


def validate_intent(intent: str) -> str:
    """Validate optional author intent, returning it unchanged."""
    try:
        size = len(intent.encode("utf-8"))
    except UnicodeEncodeError:
        raise InputError(
            "INVALID_ENCODING", "Author intent is not valid UTF-8 text."
        ) from None
    if size > MAX_INTENT_BYTES:
        raise InputError(
            "INPUT_TOO_LARGE",
            f"Author intent is {size} UTF-8 bytes; the limit is "
            f"{MAX_INTENT_BYTES:,} bytes.",
        )
    if _has_sensitive_content(intent):
        raise InputError(
            "SENSITIVE_INPUT",
            "Author intent contains recognizable credential material. "
            "Remove it before requesting a draft.",
        )
    return intent


def _run_git(args: list[str], cwd: Path, limit: int, description: str) -> bytes:
    """Run one fixed Git command, reading at most ``limit`` bytes."""
    try:
        # Product calls use Git; test probes pass a small Python emitter through
        # this bounded reader to verify byte and timeout behavior.
        command = [_GIT, "-c", "core.fsmonitor=false", *args[1:]] if args[0] == _GIT else args
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=_git_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            bufsize=0,
        )
    except OSError:
        raise InputError(
            "GIT_FAILED", f"Git could not start while {description}."
        ) from None

    assert process.stdout is not None
    output = bytearray()
    selector = selectors.DefaultSelector()
    deadline = time.monotonic() + GIT_TIMEOUT_SECONDS
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        fd = process.stdout.fileno()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _timeout_error(description)
            if not selector.select(remaining):
                raise _timeout_error(description)

            chunk = os.read(fd, min(65_536, limit + 1 - len(output)))
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > limit:
                raise InputError(
                    "INPUT_TOO_LARGE",
                    f"Git output exceeded the {limit:,}-byte limit while "
                    f"{description}.",
                )

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _timeout_error(description)
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            raise _timeout_error(description) from None
        if returncode != 0:
            raise InputError("GIT_FAILED", f"Git failed while {description}.")
        return bytes(output)
    finally:
        selector.close()
        process.stdout.close()
        if process.poll() is None:
            process.kill()
        process.wait()


def _timeout_error(description: str) -> InputError:
    return InputError(
        "GIT_TIMEOUT",
        f"Git timed out after {GIT_TIMEOUT_SECONDS:g} seconds while {description}.",
    )


def _git_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in _CLEARED_GIT_VARIABLES
    }
    environment.update(
        {
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "cat",
            "PAGER": "cat",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return environment


def _parse_raw_metadata(raw: bytes) -> tuple[ChangedFile, ...]:
    records = raw.split(b"\0")
    if records and records[-1] == b"":
        records.pop()
    if len(records) % 2 != 0:
        raise InputError("GIT_FAILED", "Git returned unexpected staged metadata.")

    count = len(records) // 2
    if count == 0:
        raise InputError(
            "NO_STAGED_CHANGES",
            "No staged changes were found. Select and stage the files to describe.",
        )
    if count > MAX_CHANGED_PATHS:
        raise InputError(
            "INPUT_TOO_LARGE",
            f"Staged change includes {count} paths; the limit is "
            f"{MAX_CHANGED_PATHS}. Stage a smaller change.",
        )

    files: list[ChangedFile] = []
    for offset in range(0, len(records), 2):
        header = records[offset]
        path_bytes = records[offset + 1]
        if not header.startswith(b":"):
            raise InputError(
                "GIT_FAILED", "Git returned unexpected staged metadata."
            )
        try:
            fields = header[1:].decode("ascii").split(" ")
        except UnicodeDecodeError:
            raise InputError(
                "INVALID_ENCODING", "Git staged metadata is not valid UTF-8."
            ) from None
        if len(fields) != 5:
            raise InputError(
                "GIT_FAILED", "Git returned unexpected staged metadata."
            )
        old_mode, new_mode, _old_oid, _new_oid, status = fields

        if status in _UNMERGED_STATUSES or "U" in status:
            raise InputError(
                "INDEX_UNMERGED",
                "The index contains unresolved merge conflicts. Resolve them "
                "before requesting a draft.",
            )

        path = _decode_changed_path(path_bytes)
        _validate_modes(path, old_mode, new_mode, status)
        if status not in _ALLOWED_STATUSES:
            raise InputError(
                "UNSUPPORTED_CHANGE",
                f"Staged path {path!r} has unsupported Git status {status!r}.",
            )
        if _is_sensitive_path(path):
            raise InputError(
                "SENSITIVE_INPUT",
                f"Staged path {path!r} matches a protected-file rule and cannot "
                "be sent for draft generation.",
            )
        files.append(
            ChangedFile(
                path=path,
                old_mode=old_mode,
                new_mode=new_mode,
                status=status,
            )
        )
    return tuple(files)


def _decode_changed_path(raw: bytes) -> str:
    try:
        path = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise InputError(
            "INVALID_ENCODING", "A staged path is not valid UTF-8."
        ) from None
    if not path:
        raise InputError("UNSUPPORTED_CHANGE", "A staged path is empty.")
    if any(
        ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F
        for character in path
    ):
        raise InputError(
            "UNSUPPORTED_CHANGE",
            f"Staged path {path!r} contains control characters.",
        )
    if path.startswith("/") or any(
        part in {"", ".", ".."} for part in path.split("/")
    ):
        raise InputError(
            "UNSUPPORTED_CHANGE",
            f"Staged path {path!r} is not a safe repository-relative path.",
        )
    return path


def _validate_modes(
    path: str, old_mode: str, new_mode: str, status: str
) -> None:
    if status == "T":
        raise InputError(
            "UNSUPPORTED_CHANGE",
            f"Staged path {path!r} is a type change. Only additions, "
            "modifications, and deletions of regular files are supported.",
        )
    if old_mode == "120000" or new_mode == "120000":
        raise InputError(
            "UNSUPPORTED_CHANGE",
            f"Staged path {path!r} is a symbolic link. Symlink changes are not "
            "supported.",
        )
    if old_mode == "160000" or new_mode == "160000":
        raise InputError(
            "UNSUPPORTED_CHANGE",
            f"Staged path {path!r} is a submodule. Submodule changes are not "
            "supported.",
        )
    if old_mode not in _ALLOWED_MODES or new_mode not in _ALLOWED_MODES:
        raise InputError(
            "UNSUPPORTED_CHANGE",
            f"Staged path {path!r} has an unsupported file mode.",
        )
    if status == "A" and (
        old_mode != "000000" or new_mode not in _REGULAR_MODES
    ):
        raise InputError(
            "UNSUPPORTED_CHANGE",
            f"Staged path {path!r} has inconsistent Git metadata.",
        )
    if status == "D" and (
        new_mode != "000000" or old_mode not in _REGULAR_MODES
    ):
        raise InputError(
            "UNSUPPORTED_CHANGE",
            f"Staged path {path!r} has inconsistent Git metadata.",
        )
    if status == "M" and (
        old_mode not in _REGULAR_MODES or new_mode not in _REGULAR_MODES
    ):
        raise InputError(
            "UNSUPPORTED_CHANGE",
            f"Staged path {path!r} has inconsistent Git metadata.",
        )


def _is_sensitive_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].casefold()
    if name == ".env":
        return True
    if name.startswith(".env.") and name != ".env.example":
        return True
    if name.endswith(".pem"):
        return True
    if name.endswith(".key"):
        return True
    if name == "credentials.json":
        return True
    return name.startswith("service-account") and name.endswith(".json")


def _has_sensitive_content(text: str) -> bool:
    if _PRIVATE_KEY_RE.search(text):
        return True
    for match in _CREDENTIAL_ASSIGNMENT_RE.finditer(text):
        # Match an identifier once, then classify it. Searching for a suffix
        # inside a greedy prefix backtracks quadratically on long source lines.
        if not match.group("name").upper().endswith(
            ("API_KEY", "ACCESS_TOKEN", "AUTH_TOKEN", "CLIENT_SECRET", "PASSWORD")
        ):
            continue
        # Do not consume ordinary assignment values: they may contain nested
        # credential assignments. Horizontal whitespace also leaves empty
        # assignments empty instead of treating the next line as their value.
        value_match = _CREDENTIAL_VALUE_RE.match(text, match.end())
        if value_match is None:
            continue
        value = value_match.group().strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in "\"'"
        ):
            value = value[1:-1].strip()
        if len(value) < 8:
            continue
        if value.casefold() in _CREDENTIAL_PLACEHOLDERS:
            continue
        return True
    return _TOKEN_RE.search(text) is not None


def _has_binary_marker(patch: bytes) -> bool:
    return b"\0" in patch or _BINARY_MARKER_RE.search(patch) is not None


def _load_template(root: Path) -> tuple[str, str | None]:
    for source in _TEMPLATE_CANDIDATES:
        candidate = root / source
        try:
            entry = os.lstat(candidate)
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError:
            raise InputError(
                "TEMPLATE_INVALID",
                f"PR template {source!r} cannot be read.",
            ) from None

        if stat.S_ISLNK(entry.st_mode):
            raise InputError(
                "TEMPLATE_UNSAFE",
                f"PR template {source!r} is a symbolic link, which is not "
                "supported.",
            )
        if not stat.S_ISREG(entry.st_mode):
            raise InputError(
                "TEMPLATE_INVALID",
                f"PR template {source!r} is not a regular file.",
            )

        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            raise InputError(
                "TEMPLATE_INVALID",
                f"PR template {source!r} cannot be resolved.",
            ) from None
        if not resolved.is_relative_to(root):
            raise InputError(
                "TEMPLATE_UNSAFE",
                f"PR template {source!r} resolves outside the repository.",
            )

        data = _read_template_file(resolved, source)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise InputError(
                "TEMPLATE_INVALID",
                f"PR template {source!r} is not valid UTF-8.",
            ) from None
        if _has_forbidden_control(text):
            raise InputError(
                "TEMPLATE_INVALID",
                f"PR template {source!r} contains control characters.",
            )
        return text, source
    return FALLBACK_TEMPLATE, None


def _read_template_file(path: Path, source: str) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise InputError(
            "TEMPLATE_INVALID", f"PR template {source!r} cannot be read."
        ) from None

    try:
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise InputError(
                    "TEMPLATE_INVALID",
                    f"PR template {source!r} is not a regular file.",
                )
            if info.st_size > MAX_TEMPLATE_BYTES:
                raise InputError(
                    "INPUT_TOO_LARGE",
                    f"PR template {source!r} exceeds the "
                    f"{MAX_TEMPLATE_BYTES:,}-byte limit.",
                )

            data = bytearray()
            while len(data) <= MAX_TEMPLATE_BYTES:
                chunk = os.read(
                    descriptor,
                    min(65_536, MAX_TEMPLATE_BYTES + 1 - len(data)),
                )
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) > MAX_TEMPLATE_BYTES:
                raise InputError(
                    "INPUT_TOO_LARGE",
                    f"PR template {source!r} exceeds the "
                    f"{MAX_TEMPLATE_BYTES:,}-byte limit.",
                )
            return bytes(data)
        except OSError:
            raise InputError(
                "TEMPLATE_INVALID",
                f"PR template {source!r} cannot be read.",
            ) from None
    finally:
        os.close(descriptor)


def _has_forbidden_control(text: str) -> bool:
    return any(
        0x7F <= ord(character) <= 0x9F
        or (ord(character) < 0x20 and character not in "\n\r\t")
        for character in text
    )
