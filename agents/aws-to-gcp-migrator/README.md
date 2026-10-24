# AWS-to-GCP Migration Agent (`aws-to-gcp-migrator`)

> An autonomous AI agent that ingests AWS Infrastructure-as-Code (Terraform & architecture definitions) and converts them into production-ready, idiomatic Google Cloud Platform (GCP) configurations and architectural migration reports.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Enterprises and cloud developers actively seeking to migrate workloads to Google Cloud lack automated tools to translate complex AWS infrastructure (Terraform, Lambda functions, S3 policies, SQS, ECS Fargate) into Google Cloud native equivalents. Manual translation is time-consuming, error-prone, and often fails to leverage GCP-specific advantages like Cloud Run request concurrency or Uniform Bucket-Level Access.
- **Intended Users**: Cloud architects, DevOps/SRE engineers, platform teams, and developers migrating applications from AWS to Google Cloud.

### Key Features
- **Automated Resource Translation**: Automatically maps AWS resources (`aws_s3_bucket`, `aws_lambda_function`, `aws_sqs_queue`, `aws_ecs_task_definition`, `aws_db_instance`, `aws_iam_role`) into idiomatic GCP resources (`google_storage_bucket`, `google_cloudfunctions2_function`, `google_pubsub_topic`, `google_cloud_run_v2_service`, `google_sql_database_instance`, `google_service_account`).
- **AI-Powered Architectural Synthesis**: Uses Google Gemini 2.5 Flash to critique architectures, recommend concurrency/networking improvements, and optimize resource sizing.
- **100% Free & Zero-Cost Offline Mode**: Built-in deterministic rule engine allows complete execution and testing with `--mock` without requiring any API keys or incurring costs.
- **Actionable Migration Reports**: Generates a comprehensive `migration_report.md` detailing architecture mappings, required Google Cloud APIs to enable (`gcloud services enable`), and free-tier cost benefits.
- **Security & IAM Hardening**: Enforces Google Cloud best practices by default, including Uniform Bucket-Level Access, isolated service accounts, and Workload Identity guidance.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+ (tested on Python 3.13)
- **Agent Framework / Core Library**: Custom Agent Architecture with Google GenAI SDK (`google-genai`)
- **Models**: Google Gemini 2.5 Flash / Gemini 1.5 Flash (via Google AI Studio Free Tier) with deterministic rule-engine fallback
- **Dependencies**: `google-genai`, `python-dotenv`, `pytest`
- **Infrastructure Target**: Terraform Google Cloud Provider (`hashicorp/google >= 5.0`)

---

## Architecture & Data Flow

```
+--------------------------+
|  AWS Terraform / HCL     |
| (Lambda, S3, SQS, ECS)   |
+--------------------------+
             |
             v
+--------------------------+
|   TerraformParser        |  --> Extracts resource blocks, types & attributes
+--------------------------+
             |
             v
+--------------------------+
|   MigrationAgent         |
| (Gemini 2.5 Flash /      |  <-- Analyzes architecture, modernizes serverless,
|  Offline Rule Engine)    |      synthesizes security & IAM recommendations
+--------------------------+
             |
             +------------------------------+
             |                              |
             v                              v
+--------------------------+   +--------------------------+
|       main.tf            |   |   migration_report.md    |
| (Production GCP HCL)     |   | (Executive Audit & APIs) |
+--------------------------+   +--------------------------+
```

---

## Prerequisites

Before running this project, ensure you have:
- **Python**: Version 3.10 or higher.
- **Package Manager**: `pip` (Python package manager).
- *(Optional)*: **Gemini API Key** from [Google AI Studio](https://aistudio.google.com/) for LLM reasoning. (Not required if using `--mock` mode).
- *(Optional)*: **Terraform CLI & Google Cloud SDK (`gcloud`)** if you plan to deploy the generated resources.

---

## Installation & Setup

1. **Navigate to the agent directory:**
   ```bash
   cd agents/aws-to-gcp-migrator
   ```

2. **Set up a virtual environment and install dependencies:**
   ```bash
   # Create virtual environment
   python -m venv .venv

   # Activate virtual environment
   # On Windows (PowerShell):
   .venv\Scripts\activate
   # On Linux/macOS:
   source .venv/bin/activate

   # Install dependencies
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables (Optional):**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` to add your free `GEMINI_API_KEY` (if desired). If left blank, the agent runs automatically in offline rule-based mode.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | No | *None* | Google AI Studio free-tier API key for AI-driven insights |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Gemini model to use (`gemini-2.5-flash`, `gemini-1.5-flash`) |
| `GCP_PROJECT_ID` | No | `my-gcp-project` | Target Google Cloud project identifier |
| `GCP_REGION` | No | `us-central1` | Target Google Cloud region |

---

## How to Run

### 1. Quick Start (100% Free / Mock Mode - No API Key Needed)
Run the migration agent against the included AWS serverless example:

```bash
python main.py --input examples/aws_serverless.tf --output output --mock
```

### 2. Run with Live Gemini API
Provide your API key via `.env` or CLI argument:

```bash
python main.py --input examples/aws_serverless.tf --output output --project-id my-company-gcp --region us-central1
```

### 3. Run on Containerized Workload (ECS Fargate + RDS)
```bash
python main.py --input examples/aws_container_app.tf --output output --mock
```

---

## Example Input & Output

### Example Input (`examples/aws_serverless.tf`)
```hcl
resource "aws_s3_bucket" "data_ingest" {
  bucket        = "company-raw-data-ingest"
  force_destroy = true
}

resource "aws_sqs_queue" "task_queue" {
  name = "data-processing-tasks"
}

resource "aws_lambda_function" "processor" {
  function_name = "data-processor-func"
  runtime       = "python3.11"
}
```

### Example Generated Output (`output/main.tf`)
```hcl
# Google Cloud Platform (GCP) Infrastructure
# Migrated automatically by aws-to-gcp-migrator
# Target Project: devfest-demo-2026 | Region: us-central1

resource "google_project_service" "enabled_apis" {
  for_each = toset(["cloudfunctions.googleapis.com", "pubsub.googleapis.com", "storage.googleapis.com"])
  project  = "devfest-demo-2026"
  service  = each.key
  disable_on_destroy = false
}

resource "google_storage_bucket" "data_ingest" {
  name                        = "company-raw-data-ingest"
  location                    = "us-central1"
  uniform_bucket_level_access = true
  versioning { enabled = true }
}

resource "google_pubsub_topic" "task_queue_topic" {
  name = "data-processing-tasks-topic"
}

resource "google_cloudfunctions2_function" "processor" {
  name     = "data-processor-func"
  location = "us-central1"
  build_config {
    runtime = "python311"
  }
}
```

### Example Generated Migration Report (`output/migration_report.md`)
```markdown
# AWS to Google Cloud Platform Migration Report
> Target GCP Project: `devfest-demo-2026` | Region: `us-central1`

## Architecture Resource Mapping
| AWS Resource | GCP Target Service | Rationale |
| :--- | :--- | :--- |
| `aws_s3_bucket` | Cloud Storage | Uniform bucket-level access & soft delete |
| `aws_sqs_queue` | Cloud Pub/Sub | Native global routing without region peering |
| `aws_lambda_function` | Cloud Functions 2nd Gen | High concurrency (up to 1000 requests/instance) |

## Required Google Cloud Service Enablement
gcloud services enable cloudfunctions.googleapis.com pubsub.googleapis.com storage.googleapis.com
```

---

## How to Test

Run the automated test suite using `pytest`:

```bash
# Run all unit tests
pytest tests/ -v
```

Expected test output:
```
tests/test_migrator.py::test_mapper_region_and_services PASSED
tests/test_migrator.py::test_generator_terraform_and_report PASSED
tests/test_migrator.py::test_agent_mock_mode PASSED
tests/test_parser.py::test_parse_simple_s3 PASSED
tests/test_parser.py::test_parse_multiple_resources PASSED

===== 5 passed in 0.17s =====
```

---

## Known Limitations

- **Complex Custom Modules**: Deeply nested third-party Terraform registry modules (e.g., `module "vpc"`) require flattening or manual translation into `google_compute_network`.
- **Inline Custom IAM Policies**: AWS inline JSON policies with non-standard actions are mapped to Google Cloud service accounts; specialized custom roles should be audited for exact least-privilege scoping.
- **State Migration**: This agent migrates the *infrastructure topology and definitions*. Migrating active live state (`terraform.tfstate`) and cloud data requires data transfer services (e.g., GCP Storage Transfer Service).

---

## Security & Privacy Considerations

- **Zero Committed Secrets**: The repository contains no real credentials. All API keys are loaded via sanitized environment variables or flags.
- **Data Privacy**: When using the Gemini API, only infrastructure resource schemas are evaluated; no proprietary customer data or sensitive credentials are exchanged.
- **Safe by Default**: In `--mock` mode, zero outbound network requests are made.

---

## Future Improvements

- [ ] Support automated import of AWS CloudFormation templates directly to Google Cloud Deployment Manager / Terraform.
- [ ] Add direct integration with Google Cloud Storage Transfer Service for automatic S3-to-GCS bucket synchronization.
- [ ] Support generating Terragrunt / OpenTofu configurations.

---

## License

This project is contributed under the repository's [MIT License](../../LICENSE).
