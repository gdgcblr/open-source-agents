"""Invoke Semgrep and parse its JSON output. No source files are changed."""
import json
import shutil
import subprocess
from pathlib import Path
from models import Finding

class ScanError(RuntimeError):
    """Expected target, scanner, or scanner-output failure."""

def parse_semgrep_json(raw: str) -> list[Finding]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ScanError(f"Semgrep returned malformed JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("results", []), list):
        raise ScanError("Semgrep JSON has an unexpected structure.")
    try:
        return [Finding.from_semgrep(item) for item in payload.get("results", [])]
    except (TypeError, ValueError, AttributeError) as exc:
        raise ScanError(f"Could not parse Semgrep findings: {exc}") from exc

def scan_project(target: str | Path, *, mock: bool = False) -> list[Finding]:
    path = Path(target).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise ScanError(f"Target must be an existing directory: {path}")
    if mock:
        return [Finding("MOCK.demo-rule", "Mock finding for offline demonstration.",
                        "WARNING", "example.py", 1, 1)]
    executable = shutil.which("semgrep")
    if not executable:
        raise ScanError("Semgrep was not found. Install it with `python -m pip install semgrep`.")
    try:
        result = subprocess.run(
            [executable, "scan", "--json", "--config", "auto", str(path)],
            capture_output=True, text=True, timeout=600, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ScanError("Semgrep scan timed out after 10 minutes.") from exc
    except OSError as exc:
        raise ScanError(f"Could not start Semgrep: {exc}") from exc
    if result.returncode not in (0, 1):
        detail = (result.stderr or result.stdout).strip()
        raise ScanError(f"Semgrep failed (exit {result.returncode}): {detail[:1200]}")
    if not result.stdout.strip():
        raise ScanError(f"Semgrep produced no JSON output. {(result.stderr or '').strip()[:500]}")
    return parse_semgrep_json(result.stdout)
