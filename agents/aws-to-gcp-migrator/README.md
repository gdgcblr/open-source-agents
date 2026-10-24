# AWS-to-GCP Migration Agent (`aws-to-gcp-migrator`)

> An autonomous AI agent powered by a **Three-Agent Orchestration Engine** that transpiles AWS Infrastructure-as-Code (Terraform & architecture definitions) into production-ready, idiomatic Google Cloud Platform (GCP) configurations, architecture graphs, and FinOps TCO savings reports.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Enterprises and cloud developers actively seeking to migrate workloads to Google Cloud lack automated tools to translate complex AWS infrastructure (Terraform, Lambda functions, S3 policies, SQS, ECS Fargate, VPCs) into Google Cloud native equivalents. Manual translation is time-consuming, error-prone, and fails to leverage GCP-specific advantages like Global VPCs, Cloud Run request concurrency, and Free Tier benefits.
- **Intended Users**: Cloud architects, DevOps/SRE engineers, platform teams, and developers migrating applications from AWS to Google Cloud.

### Key Features
- **Three-Agent Orchestration Architecture**:
  1. **Agent 1 (Topology Parser)**: Automatically parses AWS infrastructure and builds the full dependency graph (connecting compute, storage, messaging, and databases) with sanitized Mermaid.js visualizations.
  2. **Agent 2 (GCP Refactoring Engine)**: Uses Google Gemini Flash (with resilient failover pool `gemini-3.5-flash`, `gemini-3.6-flash`, `gemini-3-flash-preview`) or deterministic offline rule-engine to transpile regional AWS resources into idiomatic GCP resources (`google_storage_bucket`, `google_cloudfunctions2_function`, `google_pubsub_topic`, `google_cloud_run_v2_service`, `google_compute_network`, `google_sql_database_instance`, `google_service_account`).
  3. **Agent 3 (FinOps Predictor)**: Calculates baseline AWS monthly cost vs. target GCP monthly cost, factoring in Google Cloud Free Tier allowances and computing the net TCO savings delta.
- **Cross-Cloud Network Gravity & AWS Exit Toll Analyzer**: Calculates exact AWS internet data egress toll charges ($0.09/GB) for leaving AWS, compares with GCP's 100% free data ingress ($0.00), and computes the exact payoff amortization timeline in days.
- **Automatic Architecture Paradox Resolver**: Resolves 4 critical AWS architectural anti-patterns:
  - *Regional VPC Sprawl* ➔ Consolidated Global VPC Network.
  - *Lambda Concurrency Starvation* ➔ Multi-stream Cloud Run (v2) concurrency (up to 1,000 reqs/instance).
  - *S3 Cross-Region Replication (CRR) Tax* ➔ Unified Dual-Region Cloud Storage buckets with 99.99% active-active SLA.
  - *SQS Long-Polling Worker Waste* ➔ Cloud Pub/Sub Push Subscriptions triggering serverless scale-to-zero Cloud Run endpoints.
- **Gemini Live Architecture Fixer (`--interactive`)**: An interactive refinement loop allowing users to dynamically modify architectures with natural language commands (e.g., adding Cloud SQL multi-zone read replicas, Cloud Armor Layer 7 WAF, KMS CMEK encryption, and Cloud NAT).
- **One-Click Dry Run Validator (`--validate`)**: Verifies generated GCP Terraform HCL against Terraform CLI (`terraform validate`) or deterministic static compiler for balanced block delimiters, provider schema, and zero unmigrated tokens.
- **Official Google Agent Development Kit (ADK) Adapter**: Provides full ADK tool declarations (`parse_infrastructure_topology`, `predict_finops_tco`, `generate_gcp_terraform`) for enterprise agent orchestration.
- **Interactive 6-Tab Presentation Dashboard (`dashboard.html`)**: Features dark-mode command center, deep-dive "Why We Chose This" architectural decision drawers, dynamic cost slider, and rendered markdown synthesis.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+ (tested on Python 3.13)
- **Agent Framework / Core Library**: Custom Three-Agent Orchestration Pipeline with Google GenAI SDK (`google-genai`)
- **Models**: Google Gemini 2.5 Flash / Gemini 1.5 Flash (via Google AI Studio Free Tier) with deterministic rule-engine fallback
- **Visualization**: Mermaid.js & HTML5/CSS3 Responsive Dashboard
- **Dependencies**: `google-genai`, `python-dotenv`, `pytest`
- **Infrastructure Target**: Terraform Google Cloud Provider (`hashicorp/google >= 5.0`)

---

## Architecture & Data Flow

```
+-------------------------------------------------------------+
|                     AWS Terraform Input                     |
|            (Lambda, S3, SQS, ECS, VPC, RDS, IAM)            |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|            AGENT 1: The Topology Graph Parser               |
|   - Maps infrastructure dependency graph                    |
|   - Generates AWS Source Topology Mermaid Diagram           |
+-------------------------------------------------------------+
                              |
              +---------------+---------------+
              |                               |
              v                               v
+-----------------------------+ +-----------------------------+
|   AGENT 3: FinOps Predictor | | AGENT 2: GCP Refactor Engine|
| - Computes AWS vs GCP TCO   | | - Transpiles to Global VPC  |
| - Applies GCP Free Tier     | | - Gemini 2.5 Flash synthesis|
| - Calculates Net $ Savings  | | - Produces main.tf HCL      |
+-----------------------------+ +-----------------------------+
              |                               |
              +---------------+---------------+
                              |
                              v
+-------------------------------------------------------------+
|                   Tri-Artifact Delivery                     |
|  1. main.tf             : Deployable GCP Terraform HCL      |
|  2. migration_report.md : Full Executive Audit & Roadmap    |
|  3. dashboard.html      : Interactive Presentation Demo     |
+-------------------------------------------------------------+
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
python main.py --input examples/aws_serverless.tf --mock --validate
```

### 2. Run on Enterprise Workload with Live Gemini API & One-Click Validation
Run against the enterprise production workload (VPC, Subnets, ECS Fargate, S3, SQS, RDS PostgreSQL, IAM):

```bash
python main.py --input examples/aws_enterprise_workload.tf --validate --project-id fintech-corp-gcp --region us-central1
```

### 3. Interactive Gemini Live Architecture "Fixer"
Launch the interactive REPL session to dynamically refine architectures using natural language:

```bash
python main.py --input examples/aws_enterprise_workload.tf --interactive
# At the [fixer] prompt:
# Enter instruction > Add read replica to Cloud SQL
# Enter instruction > Enable Google Cloud Armor WAF
```

### 4. Run via Google Agent Development Kit (ADK) Adapter
```bash
python -c "from migrator.adk_adapter import GoogleADKMigrationAgent; agent = GoogleADKMigrationAgent(); print(agent.execute_adk_pipeline('examples/aws_serverless.tf'))"
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

### Example FinOps & Network Gravity Output
```
[*] FinOps Summary:
    - Baseline AWS Cost : $147.50 / month
    - Target GCP Cost   : $79.40 / month
    - Net Monthly Saving: $68.10 / month (46.2% savings)
[*] Network Gravity Analysis:
    - AWS Exit Toll     : $45.00 (500GB @ $0.09/GB egress)
    - GCP Ingress Toll  : $0.00 (100% Free Data Ingress)
    - Toll Payoff Time  : 19.8 days via GCP savings
----------------------------------------------------------------------------
[OK] Production GCP Terraform HCL : output/main.tf
[OK] Executive Migration Audit    : output/migration_report.md
[OK] Interactive Visual Dashboard : output/dashboard.html
[OK] Validation Status            : [PASS] 100% Syntactically Valid GCP HCL (Schema & Syntax Verified)
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
tests/test_migrator.py::test_topology_agent_graph PASSED
tests/test_migrator.py::test_finops_predictor_agent PASSED
tests/test_migrator.py::test_generator_terraform_and_report PASSED
tests/test_migrator.py::test_agent_three_agent_pipeline PASSED
tests/test_migrator.py::test_google_adk_agent PASSED
tests/test_migrator.py::test_network_gravity_egress_toll PASSED
tests/test_migrator.py::test_architecture_paradox_resolver PASSED
tests/test_migrator.py::test_terraform_hcl_validator PASSED
tests/test_parser.py::test_parse_simple_s3 PASSED
tests/test_parser.py::test_parse_multiple_resources PASSED

===== 11 passed in 0.10s =====
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
