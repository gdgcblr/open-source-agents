"""RunReady diagnostic and repair tools.

Each function is a plain Python function suitable for registration as a Google
ADK tool (ADK derives the schema from the signature + docstring). Crucially,
**all enforcement lives in** :mod:`runready.policy` — these functions are thin
wrappers that gather evidence or carry out an already-approved, already-
validated action. The model chooses *which* tool to call; it can never widen
what a tool is permitted to do.

The functions here are also directly unit-testable without any LLM, which is
how the adversarial test suite proves the safety boundary.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from . import policy
from .policy import DEFAULT_LIMITS, Budget, Limits, PolicyError
from .schema import CheckResult, CheckStatus

# Files worth reading when diagnosing a Python/Cloud Run startup problem.
_INTERESTING = (
    "app.yaml",
    "Procfile",
    "Dockerfile",
    "requirements.txt",
    "pyproject.toml",
    "main.py",
)
_INTERESTING_SUFFIXES = (".py",)

# Matches a uvicorn/gunicorn-style "module:attr" startup target.
_ENTRYPOINT_RE = re.compile(r"\b(?:uvicorn|gunicorn)\s+([A-Za-z0-9_.]+):([A-Za-z0-9_]+)")


def inspect_project(root: str, budget: Budget | None = None, limits: Limits = DEFAULT_LIMITS) -> dict:
    """Enumerate and read approved files under the project root (read-only).

    Returns a mapping of workspace-relative path -> redacted file contents for
    the files most relevant to a Cloud Run startup diagnosis. Protected and
    out-of-scope paths are skipped by policy; size and count caps are enforced.

    Args:
        root: Absolute path to the one approved project root for this session.

    Returns:
        dict with keys ``files`` (path -> content) and ``skipped`` (paths the
        policy declined to read, with reasons).
    """
    bud = budget or Budget(limits=limits)
    bud.charge_tool_call()
    root_path = policy.resolve_in_workspace(root, ".")

    files: dict[str, str] = {}
    skipped: dict[str, str] = {}
    count = 0
    for path in sorted(root_path.rglob("*")):
        if not path.is_file():
            continue
        if count >= limits.max_files_inspected:
            break
        rel = path.relative_to(root_path).as_posix()
        if path.name not in _INTERESTING and path.suffix not in _INTERESTING_SUFFIXES:
            continue
        try:
            resolved = policy.resolve_in_workspace(root, rel)
            text = policy.read_text_capped(resolved, limits)
            bud.charge_bytes(len(text.encode("utf-8")))
            files[rel] = policy.redact_secrets(text)
            count += 1
        except PolicyError as exc:
            skipped[rel] = str(exc)
    return {"files": files, "skipped": skipped}


def analyze_deployment_logs(log_text: str) -> dict:
    """Extract relevant, secret-redacted error evidence from a supplied log.

    Treats the log as untrusted data. Returns the redacted error lines and a
    best-effort classification. Does not read any file itself.

    Args:
        log_text: Raw startup/deployment log text provided by the user.

    Returns:
        dict with ``error_lines`` (list[str], redacted), ``missing_module``
        (str | None), and ``classification`` (str).
    """
    redacted = policy.redact_secrets(log_text)
    error_lines = [
        ln.strip()
        for ln in redacted.splitlines()
        if any(k in ln for k in ("Error", "Traceback", "Exception", "failed", "ModuleNotFound"))
    ]
    missing = None
    m = re.search(r"No module named ['\"]([A-Za-z0-9_.]+)['\"]", redacted)
    if m:
        missing = m.group(1)
    classification = "startup_configuration" if missing else "unknown"
    return {
        "error_lines": error_lines,
        "missing_module": missing,
        "classification": classification,
    }


def check_cloudrun_config(root: str, limits: Limits = DEFAULT_LIMITS) -> dict:
    """Run deterministic Cloud Run readiness checks against the project (read-only).

    Checks performed:
      * The entrypoint's ``module:attr`` target actually resolves to a file in
        the project.
      * The entrypoint binds ``0.0.0.0`` and honours ``$PORT``.

    Args:
        root: Absolute path to the approved project root.

    Returns:
        dict with ``entrypoint`` (str | None), ``entrypoint_source`` (path),
        ``module_resolves`` (bool | None), ``expected_module_path`` (str | None),
        ``binds_all_interfaces`` (bool | None), ``honours_port`` (bool | None).
    """
    root_path = policy.resolve_in_workspace(root, ".")
    entrypoint: str | None = None
    source: str | None = None
    for candidate in ("app.yaml", "Procfile"):
        p = root_path / candidate
        if p.is_file():
            text = policy.read_text_capped(policy.resolve_in_workspace(root, candidate), limits)
            m = _ENTRYPOINT_RE.search(text)
            if m:
                entrypoint = f"{m.group(1)}:{m.group(2)}"
                source = candidate
                module_dotted = m.group(1)
                break
    if entrypoint is None:
        return {
            "entrypoint": None,
            "entrypoint_source": source,
            "module_resolves": None,
            "expected_module_path": None,
            "binds_all_interfaces": None,
            "honours_port": None,
        }

    # Resolve module:attr -> file path (module.sub -> module/sub.py or .../__init__.py)
    parts = module_dotted.split(".")
    file_rel = Path(*parts).with_suffix(".py")
    pkg_rel = Path(*parts) / "__init__.py"
    module_resolves = (root_path / file_rel).is_file() or (root_path / pkg_rel).is_file()

    # Find the *actual* module that defines a FastAPI/ASGI `app`, for the hint.
    expected: str | None = None
    for py in sorted(root_path.rglob("*.py")):
        try:
            rel = py.relative_to(root_path)
            text = policy.read_text_capped(policy.resolve_in_workspace(root, rel.as_posix()), limits)
        except PolicyError:
            continue
        if re.search(r"^\s*app\s*=\s*FastAPI\(", text, re.MULTILINE):
            dotted = ".".join(rel.with_suffix("").parts)
            expected = f"{dotted}:app"
            break

    src_text = ""
    if source:
        src_text = policy.read_text_capped(policy.resolve_in_workspace(root, source), limits)
    return {
        "entrypoint": entrypoint,
        "entrypoint_source": source,
        "module_resolves": module_resolves,
        "expected_module_path": expected,
        "binds_all_interfaces": "0.0.0.0" in src_text,
        "honours_port": "$PORT" in src_text or "PORT" in src_text,
    }


def validate_project(root: str, changed_files: list[str], limits: Limits = DEFAULT_LIMITS) -> list[CheckResult]:
    """Run bounded, fixed-template validation after a patch is applied.

    Runs ``python -m py_compile`` on each changed ``.py`` file, then an import
    check of the resolved application module. Commands are fixed templates with
    validated, in-workspace arguments — never model-supplied shell strings.
    Returns honest per-check status; a check that cannot run safely is
    ``NOT_RUN``/``SKIPPED``, never silently a pass.

    Args:
        root: Absolute path to the approved project root.
        changed_files: Workspace-relative paths that were modified.

    Returns:
        list[CheckResult]: one entry per bounded check performed.
    """
    results: list[CheckResult] = []
    for rel in changed_files:
        try:
            resolved = policy.resolve_in_workspace(root, rel)
        except PolicyError as exc:
            results.append(CheckResult(f"py_compile:{rel}", CheckStatus.NOT_RUN, str(exc)))
            continue
        if resolved.suffix != ".py":
            results.append(
                CheckResult(f"py_compile:{rel}", CheckStatus.SKIPPED, "not a Python file")
            )
            continue
        results.append(_run_bounded([sys.executable, "-m", "py_compile", str(resolved)],
                                    name=f"py_compile:{rel}", cwd=root, limits=limits))

    # Import check against the entrypoint module, if we can resolve one.
    cfg = check_cloudrun_config(root, limits)
    expected = cfg.get("expected_module_path")
    if expected:
        module = expected.split(":", 1)[0]
        results.append(
            _run_bounded(
                [sys.executable, "-c", f"import importlib; importlib.import_module({module!r})"],
                name=f"import:{module}",
                cwd=root,
                limits=limits,
            )
        )
    else:
        results.append(CheckResult("import", CheckStatus.NOT_RUN, "no resolvable app module"))
    return results


def _run_bounded(cmd: list[str], *, name: str, cwd: str, limits: Limits) -> CheckResult:
    """Execute one fixed-template command with a timeout and output cap."""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed template, list args, no shell
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=limits.subprocess_timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(name, CheckStatus.NOT_RUN, "timed out (bounded execution limit)")
    except (OSError, ValueError) as exc:
        return CheckResult(name, CheckStatus.NOT_RUN, f"could not execute: {exc}")
    out = policy.redact_secrets((proc.stdout + proc.stderr)[: limits.max_output_bytes])
    status = CheckStatus.PASSED if proc.returncode == 0 else CheckStatus.FAILED
    return CheckResult(name, status, out.strip() or f"exit={proc.returncode}")


def prepare_deployment(root: str, service_name: str = "my-service", region: str = "us-central1") -> dict:
    """Produce a suggested gcloud deploy command and a prerequisite checklist.

    Performs NO cloud mutation. The command is a suggestion for the user to run
    themselves after resolving the listed prerequisites.

    Args:
        root: Absolute path to the approved project root (validated, not mutated).
        service_name: Desired Cloud Run service name.
        region: Target region.

    Returns:
        dict with ``command`` (str) and ``prerequisites`` (list[str]).
    """
    policy.resolve_in_workspace(root, ".")  # validate scope only
    safe_name = re.sub(r"[^a-z0-9-]", "-", service_name.lower())[:63] or "my-service"
    safe_region = re.sub(r"[^a-z0-9-]", "-", region.lower())[:40] or "us-central1"
    command = (
        f"gcloud run deploy {safe_name} --source . "
        f"--region {safe_region} --allow-unauthenticated"
    )
    return {
        "command": command,
        "prerequisites": [
            "Authenticated gcloud CLI (`gcloud auth login`) and a selected project.",
            "Cloud Run and Cloud Build APIs enabled on the project.",
            "A correct startup entrypoint (apply RunReady's patch first).",
            "Billing enabled; RunReady does not create or modify any cloud resource.",
        ],
    }
