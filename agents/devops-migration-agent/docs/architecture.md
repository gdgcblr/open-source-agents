# Architecture Documentation: DevOps Migration Agent

## High-Level Architecture

The **DevOps Migration Agent** is an enterprise-grade AI-assisted DevOps migration tool powered by **Google ADK (Agent Development Kit)** and **Google Gemini 2.5 Flash**. It provides deterministic, secure, and reproducible translations of GitHub Actions workflows into Azure DevOps Pipelines.

```
                           +--------------------------------------+
                           |        CLI Entrypoint (agent.py)     |
                           +--------------------------------------+
                                             |
                     +-----------------------+-----------------------+
                     |                                               |
             [Online Mode]                                    [Offline Mode]
                     |                                               |
         +-----------------------+                                   |
         | Google ADK LlmAgent   |                                   |
         | (Gemini 2.5 Flash)    |                                   |
         +-----------------------+                                   |
                     |                                               |
         +-----------------------------------------------------------+
         |            Orchestrated Tool Execution Pipeline           |
         +-----------------------------------------------------------+
                     |
    +----------------+----------------+----------------+----------------+
    |                |                |                |                |
    v                v                v                v                v
[GitHub Parser] [Action Mapper] [ADO Generator] [TF Validator] [Risk Assessor]
    |                |                |                |                |
    +----------------+----------------+----------------+----------------+
                                     |
                                     v
                        +-------------------------+
                        |     Report Generator    |
                        +-------------------------+
                                     |
    +--------------------------------+--------------------------------+
    |                                                                 |
    v                                                                 v
Markdown Deliverables:                                     Structured JSON Data:
- generated-pipeline.yml                                   - migration-summary.json
- migration-report.md                                      - validation-results.json
- risk-assessment.md
- migration-checklist.md
```

## Architectural Components

### 1. GitHub Actions Parser (`tools/github_parser.py`)
- Employs `yaml.safe_load` to guarantee no execution of arbitrary python constructors.
- Resolves YAML 1.1 `on:` boolean handling (where unquoted `on:` evaluates to boolean `True`).
- Extracts workflow triggers, jobs, dependencies (`needs`), runners (`runs-on`), strategy matrices, steps, environment variables, and secret expressions.
- Never executes scripts.

### 2. Explainable Action Compatibility Registry (`tools/action_mapper.py`)
- Standardizes translations for core actions (`checkout`, `setup-node`, `setup-python`, `cache`, `upload-artifact`, `download-artifact`, `docker/build-push-action`, `docker/login-action`, `hashicorp/setup-terraform`, `actions/github-script`).
- Classifies each action into one of five statuses:
  - `DIRECT`: Exact Azure DevOps equivalent available.
  - `PARTIAL`: Mapped with caveats, manual inputs, or service connections required.
  - `MANUAL_MIGRATION`: Environment/API-coupled actions (such as Octokit JS).
  - `UNSUPPORTED`: Non-translatable GitHub-specific proprietary features.
  - `UNKNOWN`: Uncataloged third-party actions.
- Automatically translates GitHub `${{ ... }}` expression macros into Azure DevOps `$(...)` syntax.

### 3. Azure DevOps Pipeline Generator (`tools/ado_generator.py`)
- Uses Jinja2 templates (`templates/azure-pipelines.yml.j2`) to produce standard Azure DevOps Pipelines YAML.
- Maps virtual environment images (`ubuntu-latest`, `windows-latest`, `macOS-latest`).
- Converts multi-line scripts to `script: |`, `bash: |`, or `pwsh: |` steps without running them.
- Performs structural and syntax validation, distinguishing YAML syntax from Azure DevOps structural compliance.

### 4. Terraform Static Analysis (`tools/terraform_validator.py`)
- Analyzes `.tf` files to determine required cloud providers (`azurerm`, `aws`, `google`).
- Checks for remote state backend configuration (`azurerm` storage account).
- Flags security issues (such as plaintext secrets in `.tf` files).
- Formulates required Azure DevOps Service Connection recommendations.

### 5. Deterministic Risk Assessor (`tools/risk_assessor.py`)
- Calculates a quantitative risk score (0-100) and severity rating (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- Identifies hard blockers before cutover.
- Categorizes risk into Security, Compatibility, Infrastructure, and Operational dimensions.

### 6. Google ADK Agent (`agent.py`)
- Integrates Google ADK `Agent` (`LlmAgent`).
- Exposes tools with typed docstrings conforming to ADK tool standards.
- Augments recommendations with Gemini 2.5 Flash when online, while guaranteeing 100% deterministic local execution when offline.
