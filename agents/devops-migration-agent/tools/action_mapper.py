"""Explainable Compatibility Registry and Action Mapper.

Translates GitHub Actions to Azure DevOps pipeline tasks, built-in checkout,
or custom scripts. Provides structured classification: direct, partial,
manual_migration, unsupported, or unknown.
Never invents inputs or assumes equivalence when behaviors diverge.
"""

from __future__ import annotations

import re
from typing import Any

from models.github_workflow import WorkflowStep
from models.migration_report import ActionMappingResult, ActionMappingStatus

# Regular expressions for translating GitHub expression syntax to Azure DevOps
EXPR_SECRET_RE = re.compile(r"\$\{\{\s*secrets\.([a-zA-Z0-9_]+)\s*\}\}")
EXPR_ENV_RE = re.compile(r"\$\{\{\s*env\.([a-zA-Z0-9_]+)\s*\}\}")
EXPR_VARS_RE = re.compile(r"\$\{\{\s*vars\.([a-zA-Z0-9_]+)\s*\}\}")
EXPR_GITHUB_RE = re.compile(r"\$\{\{\s*github\.([a-zA-Z0-9_]+)\s*\}\}")

GITHUB_TO_ADO_VARS = {
    "sha": "$(Build.SourceVersion)",
    "ref": "$(Build.SourceBranch)",
    "ref_name": "$(Build.SourceBranchName)",
    "repository": "$(Build.Repository.Name)",
    "workspace": "$(Build.SourcesDirectory)",
    "actor": "$(Build.RequestedFor)",
    "run_id": "$(Build.BuildId)",
    "run_number": "$(Build.BuildNumber)",
}


def translate_expressions(text: str | None) -> str | None:
    """Translates GitHub Actions ${{ ... }} syntax into Azure DevOps $(...) macros."""
    if not text:
        return text

    # Secrets -> $(SECRET_NAME)
    text = EXPR_SECRET_RE.sub(r"$(\1)", text)

    # Env -> $(VAR_NAME)
    text = EXPR_ENV_RE.sub(r"$(\1)", text)

    # Vars -> $(VAR_NAME)
    text = EXPR_VARS_RE.sub(r"$(\1)", text)

    # GitHub context
    def _replace_github(m: re.Match[str]) -> str:
        prop = m.group(1).lower()
        return GITHUB_TO_ADO_VARS.get(prop, f"$(GitHub.{m.group(1)})")

    text = EXPR_GITHUB_RE.sub(_replace_github, text)
    return text


def map_checkout_action(step: WorkflowStep) -> ActionMappingResult:
    """Maps actions/checkout to Azure DevOps checkout: self directive."""
    with_p = step.with_params
    fetch_depth = with_p.get("fetch-depth", 1)
    submodules = with_p.get("submodules", False)
    lfs = with_p.get("lfs", False)
    clean = with_p.get("clean", True)
    persist_credentials = with_p.get("persist-credentials", True)

    ado_inputs: dict[str, Any] = {
        "checkout": "self",
        "clean": clean,
        "fetchDepth": 0 if str(fetch_depth).strip() == "0" else fetch_depth,
    }

    if submodules is True or str(submodules).lower() in ("true", "recursive"):
        ado_inputs["submodules"] = "true" if str(submodules).lower() != "recursive" else "recursive"

    if lfs:
        ado_inputs["lfs"] = "true"

    if persist_credentials:
        ado_inputs["persistCredentials"] = "true"

    warnings: list[str] = []
    if "token" in with_p:
        warnings.append(
            "actions/checkout token specified; in Azure DevOps ensure the build service "
            "account has Project Collection Build Service permissions or configure system.accesstoken."
        )

    return ActionMappingResult(
        action_name="actions/checkout",
        action_version=step.action_version,
        status=ActionMappingStatus.DIRECT,
        ado_task="checkout",
        ado_inputs=ado_inputs,
        warnings=warnings,
        explanation=(
            "Azure DevOps provides a native 'checkout: self' step. Configured checkout "
            "options including clean, fetchDepth, and submodules."
        ),
    )


def map_setup_python(step: WorkflowStep) -> ActionMappingResult:
    """Maps actions/setup-python to UsePythonVersion@0."""
    with_p = step.with_params
    py_ver = with_p.get("python-version", "3.x")
    arch = with_p.get("architecture", "x64")

    ado_inputs = {
        "versionSpec": str(py_ver),
        "addToPath": True,
        "architecture": arch,
    }

    warnings: list[str] = []
    manual_steps: list[str] = []

    if "cache" in with_p:
        cache_tool = with_p["cache"]
        warnings.append(
            f"Built-in caching for '{cache_tool}' is not bundled in UsePythonVersion@0. "
            "A separate Cache@2 task is recommended."
        )
        manual_steps.append(
            f"Add Cache@2 task before dependency installation for {cache_tool} caching."
        )

    return ActionMappingResult(
        action_name="actions/setup-python",
        action_version=step.action_version,
        status=ActionMappingStatus.DIRECT if "cache" not in with_p else ActionMappingStatus.PARTIAL,
        ado_task="UsePythonVersion@0",
        ado_inputs=ado_inputs,
        warnings=warnings,
        manual_steps=manual_steps,
        explanation=(
            "Mapped to Azure DevOps UsePythonVersion@0 task. Configures Python version "
            "and prepends interpreter to system PATH."
        ),
    )


def map_setup_node(step: WorkflowStep) -> ActionMappingResult:
    """Maps actions/setup-node to NodeTool@0."""
    with_p = step.with_params
    node_ver = with_p.get("node-version", "20.x")
    check_latest = with_p.get("check-latest", False)

    ado_inputs = {
        "versionSpec": str(node_ver),
        "checkLatest": bool(check_latest),
    }

    warnings: list[str] = []
    manual_steps: list[str] = []

    if "cache" in with_p:
        warnings.append(
            f"Built-in caching for '{with_p['cache']}' is not natively included in NodeTool@0. "
            "Cache@2 task is required for npm/yarn/pnpm caching."
        )
        manual_steps.append("Configure a Cache@2 task for ~/.npm or node_modules.")

    if "registry-url" in with_p:
        warnings.append(
            "Custom npm registry-url detected. Configure npm authenticate task (npmAuthenticate@0) "
            "with an Azure DevOps service connection."
        )
        manual_steps.append("Add npmAuthenticate@0 task for private npm feeds.")

    status = (
        ActionMappingStatus.DIRECT
        if not ("cache" in with_p or "registry-url" in with_p)
        else ActionMappingStatus.PARTIAL
    )

    return ActionMappingResult(
        action_name="actions/setup-node",
        action_version=step.action_version,
        status=status,
        ado_task="NodeTool@0",
        ado_inputs=ado_inputs,
        warnings=warnings,
        manual_steps=manual_steps,
        explanation=(
            "Mapped to Azure DevOps NodeTool@0 task to provision Node.js runtime and npm on the agent."
        ),
    )


def map_cache(step: WorkflowStep) -> ActionMappingResult:
    """Maps actions/cache to Cache@2."""
    with_p = step.with_params
    path = with_p.get("path", "")
    key = with_p.get("key", "")
    restore_keys = with_p.get("restore-keys", "")

    ado_inputs: dict[str, Any] = {
        "key": translate_expressions(str(key)),
        "path": translate_expressions(str(path)),
    }

    if restore_keys:
        ado_inputs["restoreKeys"] = str(restore_keys)

    warnings: list[str] = []
    if "hashFiles(" in str(key):
        warnings.append(
            "GitHub Actions hashFiles() expression detected in cache key. In Azure DevOps, "
            "hash syntax differs: use `key: '\"prefix\" | **/package-lock.json'` format."
        )

    return ActionMappingResult(
        action_name="actions/cache",
        action_version=step.action_version,
        status=ActionMappingStatus.PARTIAL,
        ado_task="Cache@2",
        ado_inputs=ado_inputs,
        warnings=warnings,
        manual_steps=[
            "Verify the cache key pattern against Azure DevOps Cache@2 fingerprinting rules."
        ],
        explanation="Mapped to Cache@2 pipeline caching task.",
    )


def map_upload_artifact(step: WorkflowStep) -> ActionMappingResult:
    """Maps actions/upload-artifact to PublishPipelineArtifact@1."""
    with_p = step.with_params
    name = with_p.get("name", "drop")
    path = with_p.get("path", "$(Build.SourcesDirectory)")

    ado_inputs = {
        "targetPath": translate_expressions(str(path)),
        "artifact": translate_expressions(str(name)),
        "publishLocation": "pipeline",
    }

    return ActionMappingResult(
        action_name="actions/upload-artifact",
        action_version=step.action_version,
        status=ActionMappingStatus.DIRECT,
        ado_task="PublishPipelineArtifact@1",
        ado_inputs=ado_inputs,
        warnings=[],
        explanation="Mapped to PublishPipelineArtifact@1 to publish outputs as pipeline artifacts.",
    )


def map_download_artifact(step: WorkflowStep) -> ActionMappingResult:
    """Maps actions/download-artifact to DownloadPipelineArtifact@2."""
    with_p = step.with_params
    name = with_p.get("name")
    path = with_p.get("path", "$(Pipeline.Workspace)")

    ado_inputs: dict[str, Any] = {
        "buildType": "current",
        "targetPath": translate_expressions(str(path)),
    }
    if name:
        ado_inputs["artifactName"] = translate_expressions(str(name))

    return ActionMappingResult(
        action_name="actions/download-artifact",
        action_version=step.action_version,
        status=ActionMappingStatus.DIRECT,
        ado_task="DownloadPipelineArtifact@2",
        ado_inputs=ado_inputs,
        warnings=[],
        explanation="Mapped to DownloadPipelineArtifact@2 to download published artifacts.",
    )


def map_docker_build_push(step: WorkflowStep) -> ActionMappingResult:
    """Maps docker/build-push-action to Docker@2."""
    with_p = step.with_params
    context = with_p.get("context", ".")
    file_path = with_p.get("file", "Dockerfile")
    push = with_p.get("push", False)
    tags = with_p.get("tags", "")

    ado_inputs = {
        "command": "buildAndPush" if str(push).lower() == "true" else "build",
        "Dockerfile": translate_expressions(str(file_path)),
        "buildContext": translate_expressions(str(context)),
        "containerRegistry": "$(DOCKER_SERVICE_CONNECTION)",
        "repository": "$(IMAGE_NAME)",
        "tags": translate_expressions(str(tags)),
    }

    return ActionMappingResult(
        action_name="docker/build-push-action",
        action_version=step.action_version,
        status=ActionMappingStatus.PARTIAL,
        ado_task="Docker@2",
        ado_inputs=ado_inputs,
        warnings=[
            "Docker@2 requires a Docker Registry Service Connection configured in Azure DevOps. "
            "Configured placeholder $(DOCKER_SERVICE_CONNECTION)."
        ],
        manual_steps=[
            "Create a Docker Registry Service Connection in Azure DevOps Project Settings.",
            "Update containerRegistry input with the exact service connection alias.",
        ],
        explanation="Mapped to Azure DevOps Docker@2 task for container image build and push.",
    )


def map_docker_login(step: WorkflowStep) -> ActionMappingResult:
    """Maps docker/login-action to Docker@2 login command."""
    with_p = step.with_params
    registry = with_p.get("registry", "")

    ado_inputs = {
        "command": "login",
        "containerRegistry": "$(DOCKER_SERVICE_CONNECTION)",
    }

    return ActionMappingResult(
        action_name="docker/login-action",
        action_version=step.action_version,
        status=ActionMappingStatus.PARTIAL,
        ado_task="Docker@2",
        ado_inputs=ado_inputs,
        warnings=[
            f"Target registry '{registry or 'Docker Hub'}' requires an Azure DevOps Docker Registry service connection."
        ],
        manual_steps=[
            "Provision a Docker Registry Service Connection in Azure DevOps.",
            "Bind the service connection name to containerRegistry.",
        ],
        explanation="Mapped to Docker@2 login task using Azure DevOps service connection.",
    )


def map_setup_terraform(step: WorkflowStep) -> ActionMappingResult:
    """Maps hashicorp/setup-terraform to TerraformInstaller@0."""
    with_p = step.with_params
    tf_version = with_p.get("terraform_version", "latest")

    ado_inputs = {
        "terraformVersion": "latest" if tf_version == "latest" else str(tf_version),
    }

    return ActionMappingResult(
        action_name="hashicorp/setup-terraform",
        action_version=step.action_version,
        status=ActionMappingStatus.DIRECT,
        ado_task="TerraformInstaller@0",
        ado_inputs=ado_inputs,
        warnings=[
            "Ensure the Terraform extension by Microsoft DevLabs is installed in the Azure DevOps Organization."
        ],
        manual_steps=[
            "Install Terraform extension (ms-devlabs.custom-terraform-tasks) from the Visual Studio Marketplace.",
        ],
        explanation="Mapped to TerraformInstaller@0 to provision Terraform CLI binary on the agent.",
    )


def map_github_script(step: WorkflowStep) -> ActionMappingResult:
    """Classifies actions/github-script as manual migration."""
    script_snippet = step.with_params.get("script", "")
    single_line_snippet = re.sub(r"\s+", " ", str(script_snippet).strip())
    snippet_preview = (
        single_line_snippet[:80] + "..." if len(single_line_snippet) > 80 else single_line_snippet
    )

    return ActionMappingResult(
        action_name="actions/github-script",
        action_version=step.action_version,
        status=ActionMappingStatus.MANUAL_MIGRATION,
        ado_task=None,
        ado_inputs={},
        warnings=[
            "actions/github-script executes inline JavaScript against GitHub Octokit APIs. "
            "Azure DevOps has no drop-in Octokit execution engine."
        ],
        manual_steps=[
            "Rewrite script logic using Azure CLI ('az devops') or PowerShell with Azure DevOps REST API.",
            "Alternatively, invoke a standalone Node.js script using npm and @azure/devops-node-api.",
        ],
        explanation=(
            f"GitHub Script relies on the GitHub Octokit context. Snippet: [{snippet_preview}]. "
            "Requires manual migration to Azure DevOps REST API or Azure CLI."
        ),
    )


ACTION_DISPATCH_REGISTRY = {
    "actions/checkout": map_checkout_action,
    "actions/setup-python": map_setup_python,
    "actions/setup-node": map_setup_node,
    "actions/cache": map_cache,
    "actions/upload-artifact": map_upload_artifact,
    "actions/download-artifact": map_download_artifact,
    "docker/build-push-action": map_docker_build_push,
    "docker/login-action": map_docker_login,
    "hashicorp/setup-terraform": map_setup_terraform,
    "actions/github-script": map_github_script,
}


def map_action(step: WorkflowStep) -> ActionMappingResult:
    """Dispatches a WorkflowStep to its registered mapper or produces an unknown/unsupported result."""
    action_name = step.action_name
    if not action_name:
        raise ValueError("Step does not specify an action 'uses' attribute")

    mapper_fn = ACTION_DISPATCH_REGISTRY.get(action_name)
    if mapper_fn:
        return mapper_fn(step)

    # Specific known unsupported actions
    if action_name.startswith("github/codeql-action"):
        return ActionMappingResult(
            action_name=action_name,
            action_version=step.action_version,
            status=ActionMappingStatus.UNSUPPORTED,
            warnings=[
                "GitHub Advanced Security CodeQL action is tightly coupled to GitHub code scanning."
            ],
            manual_steps=[
                "Use Microsoft Security DevOps (MSDO) extension or SonarQube task in Azure DevOps."
            ],
            explanation="CodeQL action is unsupported directly; replace with Azure DevOps code analysis extensions.",
        )

    # Unknown 3rd party action
    return ActionMappingResult(
        action_name=action_name,
        action_version=step.action_version,
        status=ActionMappingStatus.UNKNOWN,
        warnings=[
            f"Third-party action '{action_name}' is not in the built-in Azure DevOps migration catalog."
        ],
        manual_steps=[
            f"Identify if '{action_name}' has an equivalent task in the Visual Studio Marketplace.",
            "Alternatively, convert action commands into an inline script step (bash, pwsh, or python).",
        ],
        explanation=f"Custom or community action '{action_name}' requires manual review or equivalent script implementation.",
    )
