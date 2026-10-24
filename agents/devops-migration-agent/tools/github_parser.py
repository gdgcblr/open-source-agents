"""GitHub Actions Workflow Parser.

Safely parses GitHub Actions YAML files into structured Pydantic models.
Correctly handles PyYAML's parsing of the 'on' keyword as boolean True,
safely extracts secrets references, and analyzes triggers, jobs, and steps.
Never executes scripts contained in workflow files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from models.github_workflow import (
    GitHubWorkflow,
    TriggerPullRequest,
    TriggerPush,
    TriggerSchedule,
    WorkflowJob,
    WorkflowStep,
    WorkflowTriggers,
)

SECRET_PATTERN = re.compile(r"\$\{\{\s*secrets\.([a-zA-Z0-9_]+)\s*\}\}")
ENV_REF_PATTERN = re.compile(r"\$\{\{\s*env\.([a-zA-Z0-9_]+)\s*\}\}")

# Suspicious hardcoded credential patterns for safety detection
HARDCODED_KEY_PATTERNS = [
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"github_pat_[a-zA-Z0-9_]{40,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
]


class WorkflowParseError(Exception):
    """Raised when a GitHub Actions workflow cannot be parsed."""


def _extract_on_directive(raw_yaml: dict[str, Any]) -> Any:
    """Extracts the trigger directive, handling YAML 1.1's boolean 'on' parsing.

    PyYAML parses unquoted 'on:' as Python True.
    """
    if True in raw_yaml:
        return raw_yaml[True]
    if "on" in raw_yaml:
        return raw_yaml["on"]
    if "True" in raw_yaml:
        return raw_yaml["True"]
    return None


def _parse_triggers(on_data: Any) -> WorkflowTriggers:
    """Normalizes the diverse trigger syntax variants in GitHub Actions."""
    triggers = WorkflowTriggers()
    if not on_data:
        return triggers

    # Case 1: Simple string, e.g. on: push
    if isinstance(on_data, str):
        if on_data == "push":
            triggers.push = TriggerPush()
        elif on_data == "pull_request":
            triggers.pull_request = TriggerPullRequest()
        elif on_data == "workflow_dispatch":
            triggers.workflow_dispatch = True
        else:
            triggers.custom_events.append(on_data)
        return triggers

    # Case 2: List of event names, e.g. on: [push, pull_request, workflow_dispatch]
    if isinstance(on_data, list):
        for item in on_data:
            if item == "push":
                triggers.push = TriggerPush()
            elif item == "pull_request":
                triggers.pull_request = TriggerPullRequest()
            elif item == "workflow_dispatch":
                triggers.workflow_dispatch = True
            elif isinstance(item, str):
                triggers.custom_events.append(item)
        return triggers

    # Case 3: Dictionary of event configurations
    if isinstance(on_data, dict):
        if "push" in on_data:
            push_val = on_data["push"] or {}
            branches = push_val.get("branches", []) if isinstance(push_val, dict) else []
            tags = push_val.get("tags", []) if isinstance(push_val, dict) else []
            paths = push_val.get("paths", []) if isinstance(push_val, dict) else []
            paths_ignore = push_val.get("paths-ignore", []) if isinstance(push_val, dict) else []
            triggers.push = TriggerPush(
                branches=[branches] if isinstance(branches, str) else list(branches),
                tags=[tags] if isinstance(tags, str) else list(tags),
                paths=[paths] if isinstance(paths, str) else list(paths),
                paths_ignore=[paths_ignore]
                if isinstance(paths_ignore, str)
                else list(paths_ignore),
            )

        if "pull_request" in on_data:
            pr_val = on_data["pull_request"] or {}
            branches = pr_val.get("branches", []) if isinstance(pr_val, dict) else []
            types_val = pr_val.get("types", []) if isinstance(pr_val, dict) else []
            paths = pr_val.get("paths", []) if isinstance(pr_val, dict) else []
            triggers.pull_request = TriggerPullRequest(
                branches=[branches] if isinstance(branches, str) else list(branches),
                types=[types_val] if isinstance(types_val, str) else list(types_val),
                paths=[paths] if isinstance(paths, str) else list(paths),
            )

        if "schedule" in on_data:
            sched_val = on_data["schedule"] or []
            crons = []
            if isinstance(sched_val, list):
                for item in sched_val:
                    if isinstance(item, dict) and "cron" in item:
                        crons.append(str(item["cron"]))
            triggers.schedule = TriggerSchedule(cron=crons)

        if "workflow_dispatch" in on_data:
            triggers.workflow_dispatch = True

        for k in on_data.keys():
            if k not in ("push", "pull_request", "schedule", "workflow_dispatch"):
                triggers.custom_events.append(str(k))

    return triggers


def _find_secrets_in_obj(data: Any, secrets_set: set[str]) -> None:
    """Recursively walks an object to locate ${{ secrets.XYZ }} references."""
    if isinstance(data, str):
        for match in SECRET_PATTERN.finditer(data):
            secrets_set.add(match.group(1))
    elif isinstance(data, dict):
        for v in data.values():
            _find_secrets_in_obj(v, secrets_set)
    elif isinstance(data, list):
        for item in data:
            _find_secrets_in_obj(item, secrets_set)


def detect_hardcoded_credentials(content: str) -> list[str]:
    """Detects potential raw secrets committed directly into workflow text."""
    findings = []
    for pattern in HARDCODED_KEY_PATTERNS:
        matches = pattern.findall(content)
        if matches:
            findings.append(
                f"Detected potential hardcoded credential matching pattern: {pattern.pattern}"
            )
    return findings


def parse_workflow_file(file_path: str | Path) -> GitHubWorkflow:
    """Parses a GitHub Actions workflow YAML file into a GitHubWorkflow model."""
    path = Path(file_path)
    if not path.is_file():
        raise WorkflowParseError(f"Workflow file does not exist: {file_path}")

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        raise WorkflowParseError(f"Failed to read workflow file: {exc}") from exc

    return parse_workflow_content(content, str(path))


def parse_workflow_content(content: str, source_path: str = "inline.yml") -> GitHubWorkflow:
    """Parses raw YAML text into a GitHubWorkflow model."""
    try:
        raw_data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise WorkflowParseError(f"YAML parsing syntax error: {exc}") from exc

    if not isinstance(raw_data, dict):
        raise WorkflowParseError("Workflow content does not define a valid YAML mapping")

    name = str(raw_data.get("name") or "GitHub Workflow")
    on_directive = _extract_on_directive(raw_data)
    triggers = _parse_triggers(on_directive)

    env_vars: dict[str, str] = {}
    if "env" in raw_data and isinstance(raw_data["env"], dict):
        env_vars = {str(k): str(v) for k, v in raw_data["env"].items()}

    permissions = raw_data.get("permissions", {})
    concurrency = raw_data.get("concurrency")

    jobs_data = raw_data.get("jobs", {})
    parsed_jobs: dict[str, WorkflowJob] = {}

    if isinstance(jobs_data, dict):
        for job_id, jdata in jobs_data.items():
            if not isinstance(jdata, dict):
                continue

            # Parse needs: can be string or list
            needs_raw = jdata.get("needs", [])
            if isinstance(needs_raw, str):
                needs_list = [needs_raw]
            elif isinstance(needs_raw, list):
                needs_list = [str(x) for x in needs_raw]
            else:
                needs_list = []

            # Parse strategy matrix
            strategy = jdata.get("strategy", {})
            matrix = strategy.get("matrix", {}) if isinstance(strategy, dict) else {}

            # Parse steps
            steps_list: list[WorkflowStep] = []
            raw_steps = jdata.get("steps", [])
            if isinstance(raw_steps, list):
                for s in raw_steps:
                    if not isinstance(s, dict):
                        continue
                    with_params = s.get("with", {}) if isinstance(s.get("with"), dict) else {}
                    step_env = s.get("env", {}) if isinstance(s.get("env"), dict) else {}

                    steps_list.append(
                        WorkflowStep(
                            id=s.get("id"),
                            name=s.get("name"),
                            uses=s.get("uses"),
                            run=s.get("run"),
                            shell=s.get("shell"),
                            with_params=with_params,
                            env={str(k): str(v) for k, v in step_env.items()},
                            if_condition=s.get("if"),
                            continue_on_error=bool(s.get("continue-on-error", False)),
                            timeout_minutes=s.get("timeout-minutes"),
                        )
                    )

            # Job env
            job_env = jdata.get("env", {}) if isinstance(jdata.get("env"), dict) else {}

            parsed_jobs[str(job_id)] = WorkflowJob(
                id=str(job_id),
                name=jdata.get("name"),
                runs_on=jdata.get("runs-on", "ubuntu-latest"),
                needs=needs_list,
                steps=steps_list,
                strategy_matrix=matrix if isinstance(matrix, dict) else {},
                env={str(k): str(v) for k, v in job_env.items()},
                permissions=jdata.get("permissions", {}),
                timeout_minutes=jdata.get("timeout-minutes"),
                if_condition=jdata.get("if"),
            )

    # Detect secrets across entire data structure
    secrets_set: set[str] = set()
    _find_secrets_in_obj(raw_data, secrets_set)

    return GitHubWorkflow(
        name=name,
        file_path=source_path,
        triggers=triggers,
        env=env_vars,
        permissions=permissions,
        concurrency=concurrency,
        jobs=parsed_jobs,
        detected_secrets=sorted(secrets_set),
        raw_ast=raw_data,
    )
