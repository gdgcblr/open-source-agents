"""Unit tests for Action Mapper and Compatibility Registry."""

from models.github_workflow import WorkflowStep
from models.migration_report import ActionMappingStatus
from tools.action_mapper import map_action, translate_expressions


def test_translate_expressions():
    assert translate_expressions("${{ secrets.MY_SECRET }}") == "$(MY_SECRET)"
    assert translate_expressions("${{ env.API_URL }}") == "$(API_URL)"
    assert translate_expressions("${{ vars.STAGE }}") == "$(STAGE)"
    assert translate_expressions("${{ github.sha }}") == "$(Build.SourceVersion)"
    assert translate_expressions("${{ github.ref }}") == "$(Build.SourceBranch)"
    assert translate_expressions("plain text") == "plain text"


def test_map_checkout_direct():
    step = WorkflowStep(
        uses="actions/checkout@v4",
        with_params={"fetch-depth": 0, "submodules": "recursive", "lfs": True},
    )
    result = map_action(step)
    assert result.status == ActionMappingStatus.DIRECT
    assert result.ado_task == "checkout"
    assert result.ado_inputs["checkout"] == "self"
    assert result.ado_inputs["fetchDepth"] == 0
    assert result.ado_inputs["submodules"] == "recursive"
    assert result.ado_inputs["lfs"] == "true"


def test_map_setup_python():
    step = WorkflowStep(
        uses="actions/setup-python@v5",
        with_params={"python-version": "3.12", "architecture": "x64"},
    )
    result = map_action(step)
    assert result.status == ActionMappingStatus.DIRECT
    assert result.ado_task == "UsePythonVersion@0"
    assert result.ado_inputs["versionSpec"] == "3.12"
    assert result.ado_inputs["addToPath"] is True


def test_map_setup_python_with_cache_flagged():
    step = WorkflowStep(
        uses="actions/setup-python@v5",
        with_params={"python-version": "3.11", "cache": "pip"},
    )
    result = map_action(step)
    assert result.status == ActionMappingStatus.PARTIAL
    assert any("caching" in w.lower() for w in result.warnings)


def test_map_setup_node():
    step = WorkflowStep(
        uses="actions/setup-node@v4",
        with_params={"node-version": "20.x"},
    )
    result = map_action(step)
    assert result.status == ActionMappingStatus.DIRECT
    assert result.ado_task == "NodeTool@0"
    assert result.ado_inputs["versionSpec"] == "20.x"


def test_map_cache():
    step = WorkflowStep(
        uses="actions/cache@v4",
        with_params={"path": "~/.cache", "key": "v1-cache"},
    )
    result = map_action(step)
    assert result.status == ActionMappingStatus.PARTIAL
    assert result.ado_task == "Cache@2"
    assert result.ado_inputs["key"] == "v1-cache"


def test_map_upload_artifact():
    step = WorkflowStep(
        uses="actions/upload-artifact@v4",
        with_params={"name": "binaries", "path": "dist/"},
    )
    result = map_action(step)
    assert result.status == ActionMappingStatus.DIRECT
    assert result.ado_task == "PublishPipelineArtifact@1"
    assert result.ado_inputs["artifact"] == "binaries"


def test_map_download_artifact():
    step = WorkflowStep(
        uses="actions/download-artifact@v4",
        with_params={"name": "binaries", "path": "downloads/"},
    )
    result = map_action(step)
    assert result.status == ActionMappingStatus.DIRECT
    assert result.ado_task == "DownloadPipelineArtifact@2"
    assert result.ado_inputs["artifactName"] == "binaries"


def test_map_docker_build_push():
    step = WorkflowStep(
        uses="docker/build-push-action@v5",
        with_params={"context": ".", "push": True, "tags": "app:v1"},
    )
    result = map_action(step)
    assert result.status == ActionMappingStatus.PARTIAL
    assert result.ado_task == "Docker@2"
    assert result.ado_inputs["command"] == "buildAndPush"
    assert len(result.manual_steps) > 0


def test_map_docker_login():
    step = WorkflowStep(
        uses="docker/login-action@v3",
        with_params={"registry": "ghcr.io"},
    )
    result = map_action(step)
    assert result.status == ActionMappingStatus.PARTIAL
    assert result.ado_task == "Docker@2"
    assert result.ado_inputs["command"] == "login"


def test_map_setup_terraform():
    step = WorkflowStep(
        uses="hashicorp/setup-terraform@v3",
        with_params={"terraform_version": "1.8.0"},
    )
    result = map_action(step)
    assert result.status == ActionMappingStatus.DIRECT
    assert result.ado_task == "TerraformInstaller@0"
    assert result.ado_inputs["terraformVersion"] == "1.8.0"


def test_map_github_script():
    step = WorkflowStep(
        uses="actions/github-script@v7",
        with_params={"script": "console.log('test')"},
    )
    result = map_action(step)
    assert result.status == ActionMappingStatus.MANUAL_MIGRATION
    assert result.ado_task is None
    assert len(result.manual_steps) > 0


def test_map_unsupported_action():
    step = WorkflowStep(uses="github/codeql-action/init@v3")
    result = map_action(step)
    assert result.status == ActionMappingStatus.UNSUPPORTED


def test_map_unknown_action():
    step = WorkflowStep(uses="custom-org/custom-action@v1")
    result = map_action(step)
    assert result.status == ActionMappingStatus.UNKNOWN
