# DevOps Migration Agent

> Autonomous Google ADK-powered AI agent that analyzes, assesses, and migrates GitHub Actions CI/CD workflows and Terraform configurations into production-ready Azure DevOps Pipelines.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Migrating CI/CD pipelines between cloud ecosystems is notoriously error-prone, manually intensive, and fraught with security risks. Engineers frequently struggle with divergent action ecosystems, secret references, unequivalent syntax, and complex multi-job dependencies.
- **Intended Users**: Platform engineers, DevOps specialists, cloud architects, and security leads looking to accelerate enterprise migration from GitHub Actions to Azure DevOps.

### Key Features
- **Deterministic Action Mapping**: Automatically translates 10+ core GitHub Actions (`checkout`, `setup-python`, `setup-node`, `cache`, `upload-artifact`, `download-artifact`, `docker/build-push-action`, `docker/login-action`, `hashicorp/setup-terraform`, `actions/github-script`) to native Azure DevOps tasks.
- **Explainable Compatibility Classification**: Transparently tags every action as `DIRECT`, `PARTIAL`, `MANUAL_MIGRATION`, `UNSUPPORTED`, or `UNKNOWN`.
- **Google ADK & Gemini 2.5 Flash**: Orchestrates modular static analysis tools using Google ADK and enriches modernization decisions with Gemini 2.5 Flash.
- **Zero-Secret Static Scanning**: Safely extracts secret references into Azure Key Vault variable group pointers without ever exposing or leaking credentials.
- **Terraform Static Analysis**: Scans `.tf` configurations to identify cloud providers, remote state storage, and required Azure DevOps Service Connections.
- **Quantitative Risk Scoring**: Computes a normalized risk score (0-100) and severity rating (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), clearly pinpointing deployment blockers.
- **Offline Mode**: Operates 100% deterministically in air-gapped environments without external API calls or credentials.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+ / Python 3.12
- **Agent Framework & Core Library**: Google Agent Development Kit (`google-adk` 2.13.0+)
- **LLM Reasoning**: Google Gemini 2.5 Flash (`gemini-2.5-flash` via `google-genai`)
- **Data Modeling & Validation**: Pydantic v2, PyYAML, jsonschema
- **Templating & CLI**: Jinja2, Rich
- **Quality & Testing**: pytest, pytest-cov, ruff

---

## Architecture & Data Flow

```
+------------------------------------------------------------------------+
|                      DevOps Migration Agent CLI                        |
|                               (agent.py)                               |
+------------------------------------------------------------------------+
                                    |
          +-------------------------+-------------------------+
          |                                                   |
   [Online Mode]                                       [Offline Mode]
          |                                                   |
+-------------------+                                         |
|  Google ADK Agent |                                         |
| (Gemini 2.5 Flash)|                                         |
+-------------------+                                         |
          |                                                   |
          +-------------------------+-------------------------+
                                    |
+------------------------------------------------------------------------+
|                  Orchestrated Tool Execution Pipeline                  |
+------------------------------------------------------------------------+
  |                   |                   |               |
  v                   v                   v               v
[github_parser] [action_mapper] [terraform_validator] [risk_assessor]
  |                   |                   |               |
  +-------------------+---------+---------+---------------+
                                |
                                v
                       [ado_generator]
                                |
                                v
                       [report_generator]
                                |
+------------------------------------------------------------------------+
|                          Generated Artifacts                           |
+------------------------------------------------------------------------+
  ├── generated-pipeline.yml       (Production Azure DevOps Pipeline YAML)
  ├── migration-report.md          (Comprehensive migration documentation)
  ├── risk-assessment.md           (Quantitative risk scoring & blockers)
  ├── migration-checklist.md        (Step-by-step phased execution plan)
  ├── migration-summary.json       (Machine-readable metrics data)
  └── validation-results.json      (Structural & YAML syntax validation)
```

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.11 or higher installed (`python --version`)
- Python package manager (`pip` or `uv`)
- *(Optional for online mode)* Google Gemini API Key (`GOOGLE_API_KEY`) from [Google AI Studio](https://aistudio.google.com/)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/devops-migration-agent
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   # Windows (PowerShell):
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables (Optional for online mode):**
   ```bash
   cp .env.example .env
   # Edit .env and supply your GOOGLE_API_KEY
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | No (for offline) | *None* | Google AI Studio API key for Gemini 2.5 Flash |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Identifier for the Gemini model |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | `false` | Enable Vertex AI backend instead of AI Studio |
| `GOOGLE_CLOUD_PROJECT` | No | *None* | Google Cloud Project ID (when using Vertex AI) |
| `OFFLINE_MODE` | No | `false` | Force offline deterministic execution |
| `AZURE_SERVICE_CONNECTION` | No | `azure-service-connection` | Default Azure DevOps ARM service connection name |
| `DEFAULT_VM_IMAGE` | No | `ubuntu-latest` | Default virtual machine runner pool image |
| `MIGRATION_OUTPUT_DIR` | No | `./migration-output` | Default directory for generated deliverables |

---

## How to Run

### 1. Documented Offline Command
Execute the full migration pipeline in offline mode without requiring API keys:

```bash
python agent.py \
  --workflow samples/github-action-example.yml \
  --output ./migration-output \
  --offline
```

### 2. Including Terraform Static Analysis
Include Terraform directory scanning to detect required cloud service connections and backend state storage:

```bash
python agent.py \
  --workflow samples/github-action-example.yml \
  --output ./migration-output \
  --terraform samples/terraform-example \
  --offline
```

### 3. Online Execution with Google ADK and Gemini
Run with Google ADK agent orchestration and Gemini 2.5 Flash recommendations:

```bash
export GOOGLE_API_KEY="your-api-key"
python agent.py \
  --workflow samples/github-action-example.yml \
  --output ./migration-output \
  --model gemini-2.5-flash
```

---

## Output Contract & Generated Artifacts

Running the migration produces all required files in the specified `--output` directory:

```text
migration-output/
├── generated-pipeline.yml      # Azure DevOps Pipelines YAML
├── migration-report.md         # Component mapping and architectural report
├── risk-assessment.md          # Deterministic risk rating and blockers
├── migration-checklist.md       # Interactive pre- and post-cutover checklist
├── migration-summary.json      # Structured summary matching JSON schema
└── validation-results.json     # Syntax and structural validation log
```

### Validation Contract
- **Structural YAML Validation**: Distinguishes basic YAML syntax checking from Azure DevOps structural rules (e.g., verifying `jobs`, `pool.vmImage`, and non-empty `steps`).
- **Schema Compliance**: `migration-summary.json` is strictly validated against `schemas/migration-summary.schema.json`.

---

## Testing & Verification

The project includes 44 unit and integration tests with **88% code coverage**.

Run the full test suite:
```bash
pytest --cov=. --cov-report=term-missing
```

Run code formatting and lint verification:
```bash
ruff check .
ruff format --check .
```

---

## Documentation Index

- [Architecture Overview](docs/architecture.md)
- [Security & Threat Model](docs/security.md)
- [Action Compatibility Registry](docs/compatibility.md)
- [Known Limitations](docs/limitations.md)

---

## License

This project is licensed under the MIT License - see the repository [LICENSE](../../LICENSE) file for details.
