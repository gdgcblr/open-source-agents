"""Deterministic, local checks for common Cloud Run deployment blockers."""

from pathlib import Path
import re


RUNTIME_MANIFESTS = ("requirements.txt", "pyproject.toml", "package.json", "go.mod")
IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "test",
    "tests",
}
MAX_SOURCE_BYTES = 1024 * 1024
PYTHON_SERVER_PATTERN = re.compile(r"(?:\bapp|\bapplication)\.run\s*\(|\buvicorn\.run\s*\(")


def _finding(severity, check, message, detail=""):
    return {
        "severity": severity,
        "check": check,
        "message": message,
        "detail": detail,
    }


def _read_source_files(root, suffix):
    for path in root.rglob("*{}".format(suffix)):
        if any(part.lower() in IGNORED_DIRECTORIES for part in path.relative_to(root).parts):
            continue
        if path.name.startswith("test_"):
            continue
        try:
            if path.is_file() and path.stat().st_size <= MAX_SOURCE_BYTES:
                yield path, path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue


def _check_python_listener(root):
    findings = []
    candidates = list(_read_source_files(root, ".py"))
    for path, source in candidates:
        if not PYTHON_SERVER_PATTERN.search(source):
            continue

        relative_path = path.relative_to(root)
        if "0.0.0.0" not in source:
            findings.append(
                _finding(
                    "WARNING",
                    "PYTHON_BIND_ADDRESS",
                    "{} starts a server without an obvious 0.0.0.0 bind address.".format(
                        relative_path
                    ),
                    "Confirm the server binds to 0.0.0.0 so Cloud Run can reach it.",
                )
            )
        if "PORT" not in source:
            findings.append(
                _finding(
                    "WARNING",
                    "PYTHON_PORT",
                    "{} starts a server without an obvious PORT environment setting.".format(
                        relative_path
                    ),
                    "Cloud Run provides the listening port in the PORT environment variable.",
                )
            )
    return findings


def _check_dockerfile(root):
    dockerfile = root / "Dockerfile"
    if not dockerfile.is_file():
        return [
            _finding(
                "INFO",
                "BUILD_METHOD",
                "No Dockerfile found; a supported source project can still deploy with buildpacks.",
                "Add a Dockerfile only when you need to control the container build explicitly.",
            )
        ]

    try:
        content = dockerfile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [
            _finding("ERROR", "DOCKERFILE_READ", "Dockerfile exists but could not be read.")
        ]

    has_start_command = any(
        line.strip().upper().startswith(("CMD ", "ENTRYPOINT "))
        for line in content.splitlines()
    )
    if has_start_command:
        return [_finding("PASS", "DOCKERFILE_START", "Dockerfile defines a startup command.")]
    return [
        _finding(
            "ERROR",
            "DOCKERFILE_START",
            "Dockerfile has no CMD or ENTRYPOINT startup command.",
            "Add a command that starts the web process and listens on the Cloud Run PORT.",
        )
    ]


def scan_project(root):
    """Return a list of findings for the project directory at *root*."""
    root = Path(root).resolve()
    findings = []
    manifests = [name for name in RUNTIME_MANIFESTS if (root / name).is_file()]

    if manifests:
        findings.append(
            _finding(
                "PASS",
                "RUNTIME_MANIFEST",
                "Found runtime manifest(s): {}.".format(", ".join(manifests)),
            )
        )
    else:
        findings.append(
            _finding(
                "ERROR",
                "RUNTIME_MANIFEST",
                "No supported runtime manifest found.",
                "Expected one of: {}.".format(", ".join(RUNTIME_MANIFESTS)),
            )
        )

    findings.extend(_check_dockerfile(root))
    findings.extend(_check_python_listener(root))

    if (root / "package.json").is_file():
        js_sources = list(_read_source_files(root, ".js")) + list(
            _read_source_files(root, ".ts")
        )
        server_sources = [(path, text) for path, text in js_sources if ".listen(" in text]
        for path, source in server_sources:
            if "process.env.PORT" not in source:
                findings.append(
                    _finding(
                        "WARNING",
                        "NODE_PORT",
                        "{} appears to start a server without process.env.PORT.".format(
                            path.relative_to(root)
                        ),
                        "Read the listening port from Cloud Run's PORT environment variable.",
                    )
                )

    return findings