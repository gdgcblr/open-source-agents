# Action Compatibility Matrix & Registry

This document lists the baseline compatibility mappings supported by the DevOps Migration Agent.

| GitHub Action | Target Azure DevOps Equivalent | Classification | Supported Capabilities | Caveats / Required Setup |
| :--- | :--- | :--- | :--- | :--- |
| `actions/checkout` | `checkout: self` | **DIRECT** | Branch, fetchDepth, clean, submodules, lfs | In ADO, submodules require Project Collection Build Service access. |
| `actions/setup-python` | `UsePythonVersion@0` | **DIRECT** / **PARTIAL** | versionSpec, architecture, addToPath | If `cache: pip` was used in GHA, a separate `Cache@2` task is required. |
| `actions/setup-node` | `NodeTool@0` | **DIRECT** / **PARTIAL** | versionSpec, checkLatest | Custom registry credentials require `npmAuthenticate@0`. |
| `actions/cache` | `Cache@2` | **PARTIAL** | key, path, restoreKeys | GHA `hashFiles()` syntax must be converted to ADO fingerprint format (`'prefix' \| **/package-lock.json`). |
| `actions/upload-artifact` | `PublishPipelineArtifact@1` | **DIRECT** | targetPath, artifact, publishLocation | Drop artifact storage in Azure Pipelines runs. |
| `actions/download-artifact` | `DownloadPipelineArtifact@2` | **DIRECT** | buildType, targetPath, artifactName | Downloads published pipeline artifacts. |
| `docker/build-push-action` | `Docker@2` | **PARTIAL** | command: buildAndPush, Dockerfile, buildContext, tags | Requires an Azure DevOps Docker Registry Service Connection. |
| `docker/login-action` | `Docker@2` | **PARTIAL** | command: login, containerRegistry | Requires an Azure DevOps Docker Registry Service Connection. |
| `hashicorp/setup-terraform` | `TerraformInstaller@0` | **DIRECT** | terraformVersion | Requires installing the Microsoft DevLabs Terraform extension in Azure DevOps. |
| `actions/github-script` | *Manual Implementation* | **MANUAL_MIGRATION** | — | Relies on GitHub Octokit context. Must be rewritten using Azure CLI (`az devops`) or Azure DevOps REST APIs. |
| `github/codeql-action` | *Unsupported* | **UNSUPPORTED** | — | Proprietary to GitHub Advanced Security. Replace with Microsoft Security DevOps (MSDO) or SonarQube in ADO. |
| *Custom / 3rd Party* | *Script or Marketplace Task* | **UNKNOWN** | — | Requires evaluating community extensions or rewriting as inline bash/pwsh scripts. |
