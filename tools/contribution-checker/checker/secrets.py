import re
from pathlib import Path
from .rules import Result

PATTERNS = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "OpenAI-style key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "GitHub token": re.compile(r"ghp_[A-Za-z0-9]{36}"),
    "Private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
SKIP_DIRS = {".venv", "node_modules", ".git", "__pycache__", "fixtures"}

def check_secrets(p: Path) -> Result:
    hits = []
    for f in p.rglob("*"):
        if not f.is_file() or SKIP_DIRS & set(f.parts) or f.name == ".env":
            continue
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(lines, 1):
            for name, pat in PATTERNS.items():
                if pat.search(line):
                    hits.append(f"{f.relative_to(p)}:{n} ({name})")   # location only, never the value
    return Result("secrets", not hits,
                  "No secrets detected" if not hits else f"Possible secrets: {hits}",
                  "" if not hits else "Remove them, rotate the key, load from environment variables")