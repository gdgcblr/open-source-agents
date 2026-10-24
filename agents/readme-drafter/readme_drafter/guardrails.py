"""Security guardrails for the README drafter.

The project being documented is untrusted input. It may come from the internet and
contain symlinks to your private files, hard-coded secrets, or text written to
manipulate the model (prompt injection). Every file the agent opens, every piece of
text the model sees and every README it writes goes through the checks below.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from urllib.parse import urlparse

# Never listed or read: dependencies, build output and version-control metadata.
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".adk", "dist", "build",
    ".next", ".nuxt", "target", ".idea", ".vscode", "coverage", "htmlcov", ".gradle",
}
# Credential stores: never read, and a project root containing one looks like a home folder.
SECRET_DIRS = {".ssh", ".aws", ".gnupg", ".kube", ".docker", ".azure", "gcloud"}
SECRET_FILE_PATTERNS = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks", "*.kdbx",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", "credentials", "credentials.json",
    "service-account*.json", ".npmrc", ".pypirc", ".netrc", ".pgpass", ".git-credentials",
    ".htpasswd", "*.tfstate", "*.tfstate.*", "*.tfvars", "kubeconfig", "*.ovpn",
]
ENV_TEMPLATES = (".env.example", ".env.sample", ".env.template")
CONFIG_SUFFIXES = {".yml", ".yaml", ".ini", ".cfg", ".conf", ".properties", ".toml", ".env"}

_SECRET_KEY = r"(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key|client[_-]?secret|credentials?)"
_CODE_REDACTIONS = [
    # Private key blocks.
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S),
     "[REDACTED PRIVATE KEY]"),
    # Well-known token formats: OpenAI/Anthropic, Google, GitHub, AWS, Slack, JWT.
    (re.compile(
        r"sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}"
        r"|AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
     "[REDACTED]"),
    # Passwords inside URLs: scheme://user:password@host
    (re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^\s:/@]+:)[^\s@/]+(@)"), r"\1[REDACTED]\2"),
    # Quoted values of secret-looking keys: DB_PASSWORD = "...", "token": "..."
    # (?<!...) starts matches at the start of a name only. The matches are the same, but without it
    # the regex retries from every letter of every name, which took 7 s on a 10 MB codebase.
    (re.compile(rf"(?i)(?<![\w.-])([\w.-]*{_SECRET_KEY}[\w.-]*[\"']?\s*[:=]\s*)([\"'])(?!\$)([^\"'\n]{{4,}})\2"),
     r"\1\2[REDACTED]\2"),
]
# Unquoted values (POSTGRES_PASSWORD: value, API_KEY=value). Only applied to config-like
# text, because in source code the right-hand side is usually an expression, not a secret.
_CONFIG_REDACTION = (
    re.compile(rf"(?im)(^[ \t-]*(?:export[ \t]+|ENV[ \t]+|ARG[ \t]+)?[\w.-]*{_SECRET_KEY}[\w.-]*[ \t]*[:=][ \t]*)"
               rf"(?![$<\[{{])([^\s\"'#(){{}}\[\]]{{4,}})[ \t]*$"),
    r"\1[REDACTED]",
)

_URL_RE = re.compile(r"https?://[^\s\"'<>()\[\]{}\\`]+")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(\s*([^)\s]+)[^)]*\)")
_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(\s*([^)\s]+)[^)]*\)")
_RISKY_COMMAND_RES = [
    # Download-and-run: curl ... | bash, wget ... | sh, bash <(curl ...), PowerShell iex.
    re.compile(r"(?i)\b(?:curl|wget|iwr|irm|invoke-webrequest|invoke-restmethod)\b[^\n|]*\|\s*(?:sudo\s+)?"
               r"(?:(?:ba|z|da|k)?sh|python3?|perl|ruby|node)\b"),
    re.compile(r"(?i)\b(?:ba|z)?sh\s+<\(\s*(?:curl|wget)\b"),
    re.compile(r"(?i)\b(?:iex|invoke-expression)\b"),
    # Destructive commands.
    re.compile(r"\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*\s+(?:--no-preserve-root\s+)?(?:/|~|\$HOME)(?:\s|$|/\*)"),
    re.compile(r"\b(?:mkfs(?:\.\w+)?|dd\s+if=\S+\s+of=/dev/)"),
    # Decoding and running hidden payloads.
    re.compile(r"(?i)base64\s+(?:-d|--decode)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z)?sh\b"),
]


def is_secret_file(name: str) -> bool:
    if name in ENV_TEMPLATES:
        return False
    return any(fnmatch.fnmatch(name, pattern) for pattern in SECRET_FILE_PATTERNS)


def is_secret_name(name: str) -> bool:
    """True for setting names that usually hold a secret, such as DB_PASSWORD or OPENAI_API_KEY."""
    return re.search(rf"(?i){_SECRET_KEY}", name) is not None


def check_project_root(root: Path) -> str | None:
    """Refuses folders so broad that documenting them would expose personal files."""
    if not root.is_dir():
        return f"Project folder not found: {root}"
    home = Path.home().resolve()
    if root == home or home.is_relative_to(root):
        return f"PROJECT_DIR is {root}, which is or contains your home folder. Point it at one project folder."
    if any((root / name).is_dir() for name in (".ssh", ".aws", ".gnupg")):
        return f"PROJECT_DIR {root} contains a credential folder (.ssh, .aws or .gnupg), so it looks like a home folder."
    return None


def safe_path(root: Path, relative: str | Path) -> tuple[Path | None, str | None]:
    """Resolves `relative` inside `root`, refusing anything that could leak secrets.

    Returns (path, None) when the file may be read, or (None, reason) when it may not.
    Symlinks are resolved first, so a link pointing outside the project is refused.
    """
    requested = Path(relative)
    try:
        target = (root / requested).resolve()
    except (OSError, RuntimeError):
        return None, f"Could not resolve {relative}."
    if not target.is_relative_to(root):
        return None, "Only files inside the project folder can be read; links leading outside it are refused."
    folders = target.relative_to(root).parts[:-1]
    if any(part in SKIP_DIRS or part in SECRET_DIRS or part.endswith(".egg-info") for part in folders):
        return None, "Files in dependency, build, version-control or credential folders are not read."
    if is_secret_file(requested.name) or is_secret_file(target.name):
        return None, ("This file may contain secrets, so it is not read. "
                      "Document it as a file the user creates, for example from .env.example.")
    if not target.is_file():
        return None, f"File not found: {relative}"
    return target, None


def redact(text: str, config_like: bool = False) -> str:
    """Replaces secret-looking values with [REDACTED]; names and structure are kept."""
    for pattern, replacement in _CODE_REDACTIONS:
        text = pattern.sub(replacement, text)
    if config_like:
        text = _CONFIG_REDACTION[0].sub(_CONFIG_REDACTION[1], text)
    return text


def is_config_like(path: Path) -> bool:
    return (
        path.suffix.lower() in CONFIG_SUFFIXES
        or path.name.startswith(".env")
        or path.name in ("Dockerfile", "Makefile")
    )


def _defang(text: str) -> str:
    """Makes a quoted command or address unrunnable and unclickable (hxxps, ¦ for |)."""
    return text.replace("`", "").replace("http", "hxxp").replace("|", "¦")


def _is_unverified_url(url: str, known_hosts: set[str]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme in ("", "mailto"):  # relative links and e-mail addresses
        return False
    if parsed.scheme not in ("http", "https"):  # javascript:, data:, file: ...
        return True
    return (parsed.hostname or "").lower() not in known_hosts


def review_readme(readme: str, known_text: str) -> tuple[str, list[str]]:
    """Checks a model-written README before it is shown or saved.

    Prompt injection hidden in project files can make the model add malicious install
    commands, tracking images or secrets. This removes risky commands, images and links
    whose web address appears nowhere in the inspected project, and redacts secrets.
    Returns the cleaned README and a list of warnings for the user.
    """
    warnings = []
    known_hosts = {(urlparse(u).hostname or "").lower() for u in _URL_RE.findall(known_text)}

    def drop_image(match: re.Match) -> str:
        if not _is_unverified_url(match.group(2), known_hosts):
            return match.group(0)
        warnings.append(f"Removed an image from an address not found in the project: `{_defang(match.group(2))}`")
        return match.group(1)

    def drop_link(match: re.Match) -> str:
        if not _is_unverified_url(match.group(2), known_hosts):
            return match.group(0)
        warnings.append(f"Removed a link to an address not found in the project: `{_defang(match.group(2))}`")
        return match.group(1)

    readme = _IMAGE_RE.sub(drop_image, readme)
    readme = _LINK_RE.sub(drop_link, readme)
    for url in sorted(set(_URL_RE.findall(readme))):
        if _is_unverified_url(url, known_hosts):
            warnings.append(f"Check this address, it was not found in the project: `{_defang(url)}`")

    lines = []
    for line in readme.splitlines():
        if any(pattern.search(line) for pattern in _RISKY_COMMAND_RES):
            warnings.append(f"Removed a risky command (downloads and runs code, or deletes files): `{_defang(line.strip()[:120])}`")
            lines.append("`[removed by README Drafter: risky command]`")
        else:
            lines.append(line)
    readme = "\n".join(lines) + "\n"

    redacted = redact(readme, config_like=True)
    if redacted != readme:
        warnings.append("Redacted values that looked like passwords, keys or tokens.")
    return redacted, warnings


def warning_block(warnings: list[str]) -> str:
    """A GitHub alert listing what the safety review changed, placed above the README."""
    if not warnings:
        return ""
    items = "\n".join(f"> - {w}" for w in warnings)
    return (
        "> [!WARNING]\n"
        "> README Drafter's safety review changed this draft. Check these items, then delete this note:\n"
        f"{items}\n\n"
    )
