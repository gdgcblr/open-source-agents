"""Evidence-linked diagnosis for common Google Cloud Run log signatures."""

import re
from pathlib import Path


PATTERNS = (
    {
        "code": "PORT_BIND_FAILURE",
        "confidence": "high",
        "pattern": re.compile(
            r"failed to start and (?:then )?listen on the port|"
            r"did not start listening on the port|failed to bind.*port|"
            r"container failed to start and listen",
            re.IGNORECASE,
        ),
        "cause": "The container did not become ready on the port Cloud Run provided.",
        "next_step": (
            "Check the service startup command and confirm the web server listens "
            "on 0.0.0.0 using the PORT environment variable."
        ),
    },
    {
        "code": "MISSING_DEPENDENCY",
        "confidence": "high",
        "pattern": re.compile(
            r"ModuleNotFoundError: No module named|ImportError: No module named|"
            r"Cannot find module|Module .* not found",
            re.IGNORECASE,
        ),
        "cause": "The application failed because a required module was not available.",
        "next_step": (
            "Add the missing package to the runtime dependency manifest and verify "
            "the build installs that manifest."
        ),
    },
    {
        "code": "BUILD_DEPENDENCY_FAILURE",
        "confidence": "medium",
        "pattern": re.compile(
            r"Could not find a version that satisfies the requirement|"
            r"No matching distribution found|npm ERR!|npm error code|"
            r"ERROR: failed to build:.*buildpack|failed to solve:.*process",
            re.IGNORECASE,
        ),
        "cause": "The image build could not resolve or install a dependency.",
        "next_step": (
            "Inspect the package name, version constraints, lockfile, and build log "
            "for the first dependency error."
        ),
    },
    {
        "code": "STARTUP_COMMAND_FAILURE",
        "confidence": "medium",
        "pattern": re.compile(
            r"exec: .*executable file not found|exec format error|"
            r"/bin/sh: .*not found|command not found",
            re.IGNORECASE,
        ),
        "cause": "The configured container startup command could not be executed.",
        "next_step": (
            "Check the Dockerfile CMD/ENTRYPOINT or buildpack start command, "
            "including executable name, path, and image architecture."
        ),
    },
    {
        "code": "MEMORY_LIMIT",
        "confidence": "medium",
        "pattern": re.compile(
            r"oomkilled|out of memory|memory limit.*exceed|"
            r"memory usage.*exceed|using too much memory.*terminated",
            re.IGNORECASE,
        ),
        "cause": "The instance may have exceeded its configured memory limit.",
        "next_step": (
            "Check memory usage and workload peaks first; then optimize memory use "
            "or adjust the Cloud Run memory allocation."
        ),
    },
    {
        "code": "STARTUP_PROBE_FAILURE",
        "confidence": "medium",
        "pattern": re.compile(
            r"startup probe failed|startup probe.*failed|"
            r"health check.*failed|container failed to become healthy",
            re.IGNORECASE,
        ),
        "cause": "Cloud Run did not observe a healthy container before the startup check failed.",
        "next_step": (
            "Check startup logs, probe path and port, and whether initialization "
            "completes within the configured startup window."
        ),
    },
    {
        "code": "NO_AVAILABLE_INSTANCE",
        "confidence": "medium",
        "pattern": re.compile(
            r"request was aborted because there was no available instance|"
            r"no available container instance",
            re.IGNORECASE,
        ),
        "cause": (
            "Cloud Run could not route the request to an available instance; "
            "the service may be at its instance limit or unable to scale quickly enough."
        ),
        "next_step": (
            "Check maximum-instance limits, startup and request latency, and "
            "traffic spikes before changing scaling limits."
        ),
    },
)
SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
)

RELATED_CHECKS = {
    "PORT_BIND_FAILURE": {
        "PYTHON_BIND_ADDRESS",
        "PYTHON_PORT",
        "NODE_PORT",
    },
    "STARTUP_COMMAND_FAILURE": {"DOCKERFILE_START"},
    "MISSING_DEPENDENCY": {"RUNTIME_MANIFEST"},
    "BUILD_DEPENDENCY_FAILURE": {"RUNTIME_MANIFEST"},
}


def correlate_project_findings(diagnoses, project_findings):
    """Attach only relevant static project checks to each log diagnosis."""
    for diagnosis in diagnoses:
        related_checks = RELATED_CHECKS.get(diagnosis["check"], set())
        diagnosis["project_evidence"] = [
            {
                "check": finding["check"],
                "severity": finding["severity"],
                "message": finding["message"],
                "detail": finding["detail"],
            }
            for finding in project_findings
            if finding["check"] in related_checks
        ]
    return diagnoses


def redact_secrets(text):
    """Mask common credential formats before preserving log evidence."""
    redacted = text
    for pattern in SECRET_PATTERNS:
        if pattern.groups:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def diagnose_log_text(log_text):
    """Return diagnoses for recognized log signatures with exact line evidence."""
    diagnoses = []
    for line_number, line in enumerate(log_text.splitlines(), start=1):
        for item in PATTERNS:
            if item["pattern"].search(line):
                diagnoses.append(
                    {
                        "severity": "WARNING",
                        "check": item["code"],
                        "confidence": item["confidence"],
                        "cause": item["cause"],
                        "evidence": {
                            "line": line_number,
                            "text": redact_secrets(line.strip())[:500],
                        },
                        "next_step": item["next_step"],
                    }
                )
                break

    if diagnoses:
        return diagnoses

    nonempty_lines = [line for line in log_text.splitlines() if line.strip()]
    evidence = None
    if nonempty_lines:
        line_index = next(
            (index for index, line in enumerate(log_text.splitlines(), start=1) if line.strip()),
            1,
        )
        evidence = {
            "line": line_index,
            "text": redact_secrets(nonempty_lines[0].strip())[:500],
        }

    return [
        {
            "severity": "INFO",
            "check": "UNCLASSIFIED_LOG",
            "confidence": "none",
            "cause": "No known Cloud Run failure signature was recognized in this log.",
            "evidence": evidence,
            "next_step": (
                "Review the surrounding build or revision logs and share the relevant "
                "error context; do not treat this result as proof that the service is healthy."
            ),
        }
    ]


def diagnose_log_file(path):
    """Read a UTF-8 log file and return diagnoses, or raise an actionable error."""
    log_path = Path(path).expanduser()
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise ValueError("Cannot read log file '{}': {}".format(log_path, error)) from error
    if not content.strip():
        raise ValueError("Log file is empty: {}".format(log_path))
    return diagnose_log_text(content)