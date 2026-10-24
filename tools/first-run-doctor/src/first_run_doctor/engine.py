"""Inspection -> explicit execution -> deterministic verification -> diagnosis."""

import os
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .contract import DoctorError, contained_file, load_contract
from .diagnose import jev_diagnosis, rule_diagnosis
from .privacy import Redactor
from .runner import child_environment, copy_project, resolve_python, run_process
from .verify import observation, verify_artifacts


def check_project(
    project,
    *,
    contract_name="doctor.json",
    execute=False,
    python=None,
    environment=None,
    diagnose=False,
    env_file=None,
):
    root = Path(project).resolve()
    if not root.is_dir():
        raise DoctorError("Project directory does not exist")
    environment = dict(os.environ if environment is None else environment)
    redactor = Redactor(environment)
    contract = load_contract(root, contract_name)
    executable = resolve_python(python or sys.executable)
    command = [executable, *contract.command[1:]]
    checks = []
    entrypoint = contained_file(root, contract.command[1])
    checks.append(
        observation(
            "ENTRY",
            "Declared Python entrypoint",
            "pass" if entrypoint.is_file() else "fail",
            contract.command[1],
        )
    )
    for n, name in enumerate(contract.data["required_env"], 1):
        checks.append(
            observation(
                f"ENV{n}",
                f"Required setting {name}",
                "pass" if environment.get(name) else "fail",
                "Present" if environment.get(name) else "Missing; value is never recorded",
            )
        )
    for n, name in enumerate(contract.data["inputs"], 1):
        value = contained_file(root, name)
        checks.append(
            observation(f"INPUT{n}", "Declared input", "pass" if value.is_file() else "fail", name)
        )
    manifests = [
        name
        for name in ("pyproject.toml", "requirements.txt")
        if contained_file(root, name).is_file()
    ]
    checks.append(
        observation(
            "MANIFEST",
            "Dependency manifest",
            "pass" if manifests else "info",
            ", ".join(manifests)
            if manifests
            else "None found; stdlib-only examples may not need one",
        )
    )
    report = {
        "schema_version": 1,
        "tool_version": "0.1.0",
        "run_id": uuid.uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "project": root.name,
        "verification": "unknown",
        "contract_sha256": contract.digest,
        "command": command,
        "interpreter": {"path": executable, "version": "not queried"},
        "execution": {"status": "not_run", "returncode": None},
        "checks": checks,
        "workspace_strategy": "fresh copy excluding declared generated files; not an OS sandbox",
    }
    with tempfile.TemporaryDirectory(prefix="first-run-doctor-") as temporary:
        workspace = Path(temporary) / "project"
        workspace.mkdir()
        report["source"] = copy_project(root, workspace, contract)
        if execute and not any(c["status"] == "fail" for c in checks):
            home = Path(temporary) / "home"
            home.mkdir()
            env = child_environment(environment, contract.data["required_env"], home)
            version = run_process([executable, "--version"], workspace, env, 5, redactor)
            if version["status"] != "completed" or version["returncode"] != 0:
                raise DoctorError(
                    "Selected interpreter did not return a version within five seconds"
                )
            report["interpreter"]["version"] = version["stdout"][:256].strip()
            execution = run_process(
                command, workspace, env, contract.data["timeout_seconds"], redactor
            )
            report["execution"] = execution
            if execution["status"] == "completed":
                checks.append(
                    observation(
                        "EXEC",
                        "Command exit status",
                        "pass" if execution["returncode"] == 0 else "fail",
                        str(execution["returncode"]),
                    )
                )
                checks.extend(verify_artifacts(workspace, contract))
                statuses = {c["status"] for c in checks}
                report["verification"] = (
                    "failed"
                    if "fail" in statuses
                    else "unknown"
                    if "unknown" in statuses
                    else "verified"
                )
            else:
                checks.append(
                    observation(
                        "EXEC",
                        "Command completion",
                        "unknown",
                        "Time limit exceeded; completion unverified",
                    )
                )
        else:
            reason = (
                "Resolve failed preflight checks"
                if any(c["status"] == "fail" for c in checks)
                else "Preview only; use --execute after reviewing the command"
            )
            checks.append(observation("EXEC", "Command execution", "skipped", reason))
    report = redactor.object(report)
    report["diagnosis"] = rule_diagnosis(report)
    if diagnose:
        if not execute:
            raise DoctorError(
                "Jev diagnosis requires --execute; preview never makes network requests"
            )
        report["jev"] = jev_diagnosis(report, env_file or Path.cwd() / ".env")
    return redactor.object(report)


def exit_code(report):
    return {"verified": 0, "failed": 1, "unknown": 3}[report["verification"]]
