"""Azure DevOps Pipeline YAML Generator and Structural Validator.

Converts parsed GitHubWorkflow models and mapped actions into production-ready
Azure DevOps pipeline YAML.
Validates structural syntax and confirms Azure DevOps pipeline compliance.
Clearly distinguishes YAML syntax validation from actual Azure DevOps validation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jinja2
import yaml

from models.github_workflow import GitHubWorkflow
from models.migration_report import ActionMappingStatus, ValidationResult
from tools.action_mapper import map_action, translate_expressions

RUNNER_IMAGE_MAP = {
    "ubuntu-latest": "ubuntu-latest",
    "ubuntu-22.04": "ubuntu-22.04",
    "ubuntu-20.04": "ubuntu-20.04",
    "windows-latest": "windows-latest",
    "windows-2022": "windows-2022",
    "macos-latest": "macOS-latest",
    "macos-13": "macOS-13",
    "macos-14": "macOS-14",
}


def map_runner_image(runs_on: str | list[str]) -> str:
    """Translates GitHub Actions runs-on to Azure DevOps vmImage."""
    if isinstance(runs_on, list):
        target = runs_on[0] if runs_on else "ubuntu-latest"
    else:
        target = str(runs_on).strip()

    if target.startswith("${{") and target.endswith("}}"):
        # Matrix runner reference
        return translate_expressions(target) or "ubuntu-latest"

    return RUNNER_IMAGE_MAP.get(target.lower(), target)


def map_script_type(shell: str | None) -> str:
    """Determines appropriate Azure DevOps script step keyword."""
    if not shell:
        return "script"
    sh = shell.lower().strip()
    if sh == "bash":
        return "bash"
    if sh in ("pwsh", "powershell"):
        return "pwsh"
    return "script"


def indent_lines(text: str, spaces: int) -> str:
    """Indents lines of multi-line text for YAML blocks."""
    if not text:
        return ""
    lines = text.strip().splitlines()
    if not lines:
        return ""
    first = lines[0]
    rest = [(" " * spaces) + line for line in lines[1:]]
    return "\n".join([first] + rest)


def to_yaml_val(val: Any) -> str:
    """Formats a python value into safe inline YAML scalar."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if val is None:
        return "''"
    val_str = str(val)
    # Using json.dumps safely quotes and escapes strings for YAML
    return json.dumps(val_str)


class ADOGenerator:
    """Generates Azure DevOps Pipeline YAML from a GitHubWorkflow model."""

    def __init__(self, template_path: str | Path | None = None) -> None:
        if template_path:
            tmpl_file = Path(template_path)
            self.template_dir = tmpl_file.parent
            self.template_name = tmpl_file.name
        else:
            default_dir = Path(__file__).parent.parent / "templates"
            self.template_dir = default_dir
            self.template_name = "azure-pipelines.yml.j2"

        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.template_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        env.filters["indent_lines"] = indent_lines
        env.filters["to_yaml_val"] = to_yaml_val
        self.template = env.get_template(self.template_name)

    def generate_pipeline(self, workflow: GitHubWorkflow) -> str:
        """Converts GitHubWorkflow into Azure DevOps pipeline YAML string."""
        jobs_data = []

        for job_id, job in workflow.jobs.items():
            vm_image = map_runner_image(job.runs_on)
            job_steps = []

            for step in job.steps:
                if step.is_action:
                    mapping = map_action(step)
                    if (
                        mapping.status == ActionMappingStatus.DIRECT
                        and mapping.ado_task == "checkout"
                    ):
                        job_steps.append(
                            {
                                "type": "checkout",
                                "checkout": mapping.ado_inputs.get("checkout", "self"),
                                "clean": mapping.ado_inputs.get("clean"),
                                "fetchDepth": mapping.ado_inputs.get("fetchDepth"),
                                "submodules": mapping.ado_inputs.get("submodules"),
                                "lfs": mapping.ado_inputs.get("lfs"),
                            }
                        )
                    elif mapping.ado_task:
                        job_steps.append(
                            {
                                "type": "task",
                                "task": mapping.ado_task,
                                "displayName": step.name or f"Run {mapping.ado_task}",
                                "inputs": mapping.ado_inputs,
                                "env": {k: translate_expressions(v) for k, v in step.env.items()},
                                "condition": translate_expressions(step.if_condition),
                                "continueOnError": step.continue_on_error,
                            }
                        )
                    else:
                        job_steps.append(
                            {
                                "type": "manual_placeholder",
                                "action_name": step.action_name,
                                "displayName": step.name or f"Manual: {step.action_name}",
                                "explanation": mapping.explanation,
                            }
                        )
                elif step.is_script:
                    script_type = map_script_type(step.shell)
                    job_steps.append(
                        {
                            "type": "script",
                            "script_type": script_type,
                            "script": translate_expressions(step.run) or "",
                            "displayName": step.name or "Run command",
                            "env": {k: translate_expressions(v) for k, v in step.env.items()},
                            "condition": translate_expressions(step.if_condition),
                            "continueOnError": step.continue_on_error,
                        }
                    )

            # Process matrix if present
            matrix_dict = {}
            if job.strategy_matrix:
                matrix_name = "build_matrix"
                # If matrix has list values: e.g. python-version: ['3.10', '3.11']
                # In Azure DevOps: matrix is { py310: { python_version: '3.10' }, ... }
                # Let's create an expansion or key mapping
                first_key = next(iter(job.strategy_matrix.keys()), None)
                if first_key and isinstance(job.strategy_matrix[first_key], list):
                    for val in job.strategy_matrix[first_key]:
                        m_key = f"{first_key}_{val}".replace(".", "_").replace("-", "_")
                        matrix_dict[m_key] = {first_key: str(val)}
                else:
                    matrix_dict[matrix_name] = {
                        str(k): str(v) for k, v in job.strategy_matrix.items()
                    }

            jobs_data.append(
                {
                    "id": job.id,
                    "display_name": job.display_name,
                    "dependsOn": job.needs,
                    "condition": translate_expressions(job.if_condition),
                    "vmImage": vm_image,
                    "timeoutInMinutes": job.timeout_minutes,
                    "strategy": {"matrix": matrix_dict} if matrix_dict else None,
                    "steps": job_steps,
                }
            )

        rendered_yaml = self.template.render(
            workflow=workflow,
            pipeline_name=f"Migration-{workflow.name}".replace(" ", "-"),
            triggers=workflow.triggers,
            variables=workflow.env,
            secret_vars=workflow.detected_secrets,
            jobs=jobs_data,
        )

        return rendered_yaml


def validate_pipeline_yaml(yaml_content: str) -> ValidationResult:
    """Validates generated Azure DevOps YAML.

    Distinguishes YAML syntax validation from Azure DevOps structural compliance.
    """
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, bool] = {
        "yaml_syntax": False,
        "has_jobs_or_steps": False,
        "valid_pool_definitions": False,
        "valid_steps": False,
    }

    # 1. Check YAML syntax
    try:
        data = yaml.safe_load(yaml_content)
        checks["yaml_syntax"] = True
    except yaml.YAMLError as exc:
        errors.append(f"YAML Syntax Error: {exc}")
        return ValidationResult(
            is_valid=False,
            validation_type="Azure Pipelines Structural Validation",
            errors=errors,
            warnings=warnings,
            structural_checks=checks,
        )

    if not isinstance(data, dict):
        errors.append("Pipeline root must be a YAML dictionary mapping")
        return ValidationResult(
            is_valid=False,
            validation_type="Azure Pipelines Structural Validation",
            errors=errors,
            warnings=warnings,
            structural_checks=checks,
        )

    # 2. Check for jobs / steps / stages
    if "jobs" in data or "steps" in data or "stages" in data:
        checks["has_jobs_or_steps"] = True
    else:
        errors.append("Pipeline lacks top-level 'jobs', 'steps', or 'stages' section.")

    # 3. Check jobs structure
    if "jobs" in data and isinstance(data["jobs"], list):
        pools_valid = True
        steps_valid = True
        for idx, j in enumerate(data["jobs"]):
            if not isinstance(j, dict):
                errors.append(f"Job at index {idx} is not a valid dictionary.")
                continue
            if "job" not in j:
                errors.append(f"Job at index {idx} is missing required 'job' identifier.")
            if "pool" not in j:
                warnings.append(f"Job '{j.get('job', idx)}' does not define an explicit 'pool'.")
            else:
                pool = j["pool"]
                if not isinstance(pool, dict) or "vmImage" not in pool:
                    warnings.append(f"Job '{j.get('job')}' pool should specify 'vmImage'.")

            if "steps" not in j or not isinstance(j["steps"], list) or len(j["steps"]) == 0:
                errors.append(f"Job '{j.get('job', idx)}' has no steps defined.")
                steps_valid = False

        checks["valid_pool_definitions"] = pools_valid
        checks["valid_steps"] = steps_valid

    # 4. Trigger structural check
    if "trigger" in data:
        trig = data["trigger"]
        if trig != "none" and not isinstance(trig, (dict, list, str)):
            errors.append("Invalid 'trigger' configuration.")

    is_valid = len(errors) == 0
    return ValidationResult(
        is_valid=is_valid,
        validation_type="Azure Pipelines Structural Validation",
        errors=errors,
        warnings=warnings,
        structural_checks=checks,
    )
