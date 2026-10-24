"""
Generates idiomatic GCP Terraform configurations and comprehensive Migration Reports.
"""

from typing import List, Dict, Any
from .parser import AWSResource
from .mapper import get_service_mapping, get_gcp_region


class MigrationGenerator:
    """Generates GCP Terraform files and Markdown reports."""

    def __init__(self, project_id: str = "my-gcp-project", region: str = "us-central1"):
        self.project_id = project_id
        self.region = region

    def generate_terraform(self, resources: List[AWSResource]) -> str:
        """Constructs idiomatic GCP Terraform (HCL)."""
        tf_blocks = [
            f"""# -----------------------------------------------------------------------------
# Google Cloud Platform (GCP) Infrastructure
# Migrated automatically by aws-to-gcp-migrator
# Target Project: {self.project_id} | Region: {self.region}
# -----------------------------------------------------------------------------

terraform {{
  required_version = ">= 1.5.0"
  required_providers {{
    google = {{
      source  = "hashicorp/google"
      version = "~> 5.0"
    }}
  }}
}}

provider "google" {{
  project = "{self.project_id}"
  region  = "{self.region}"
}}
"""
        ]

        # Gather required APIs
        required_apis = set()
        for res in resources:
            mapping = get_service_mapping(res.resource_type)
            api = mapping.get("required_api")
            if api:
                required_apis.add(api)

        # Service APIs block
        if required_apis:
            apis_list = ", ".join(f'"{api}"' for api in sorted(required_apis))
            tf_blocks.append(f"""# Enable Required Google Cloud APIs
resource "google_project_service" "enabled_apis" {{
  for_each = toset([{apis_list}])
  project  = "{self.project_id}"
  service  = each.key

  disable_on_destroy = false
}}
""")

        # Translate each resource
        for res in resources:
            block = self._translate_resource(res)
            if block:
                tf_blocks.append(block)

        return "\n".join(tf_blocks)

    def _translate_resource(self, res: AWSResource) -> str:
        clean_name = res.resource_name.replace("-", "_")

        if res.resource_type == "aws_s3_bucket":
            bucket_name = res.attributes.get("bucket", f"{res.resource_name}-{self.project_id}")
            return f"""# Migrated from: {res.raw_block.splitlines()[0]}
resource "google_storage_bucket" "{clean_name}" {{
  name                        = "{bucket_name}"
  location                    = "{self.region}"
  force_destroy               = true
  uniform_bucket_level_access = true

  versioning {{
    enabled = true
  }}

  labels = {{
    environment = "migrated"
    source      = "aws-to-gcp"
  }}

  depends_on = [google_project_service.enabled_apis]
}}
"""

        elif res.resource_type == "aws_lambda_function":
            func_name = res.attributes.get("function_name", clean_name)
            return f"""# Migrated from AWS Lambda: {func_name}
# Translated to Google Cloud Functions (2nd Gen / Cloud Run)
resource "google_service_account" "{clean_name}_sa" {{
  account_id   = "{clean_name[:28]}-sa"
  display_name = "Execution Service Account for {func_name}"
}}

resource "google_cloudfunctions2_function" "{clean_name}" {{
  name        = "{func_name}"
  location    = "{self.region}"
  description = "Migrated from AWS Lambda {func_name}"

  build_config {{
    runtime     = "python311"
    entry_point = "entry_point"
    source {{
      storage_source {{
        bucket = google_storage_bucket.{clean_name}_code.name
        object = google_storage_bucket_object.{clean_name}_zip.name
      }}
    }}
  }}

  service_config {{
    max_instance_count = 100
    available_memory   = "512M"
    timeout_seconds    = 60
    service_account_email = google_service_account.{clean_name}_sa.email
  }}

  depends_on = [google_project_service.enabled_apis]
}}
"""

        elif res.resource_type == "aws_sqs_queue":
            queue_name = res.attributes.get("name", clean_name)
            return f"""# Migrated from AWS SQS Queue: {queue_name}
resource "google_pubsub_topic" "{clean_name}_topic" {{
  name = "{queue_name}-topic"
  labels = {{
    source = "aws-to-gcp"
  }}

  depends_on = [google_project_service.enabled_apis]
}}

resource "google_pubsub_subscription" "{clean_name}_sub" {{
  name  = "{queue_name}-sub"
  topic = google_pubsub_topic.{clean_name}_topic.id

  ack_deadline_seconds = 60
}}
"""

        elif res.resource_type == "aws_iam_role":
            role_name = res.attributes.get("name", clean_name)
            return f"""# Migrated from AWS IAM Role: {role_name}
resource "google_service_account" "{clean_name}" {{
  account_id   = "{role_name[:28].replace('_', '-')}"
  display_name = "Service Account for {role_name}"
}}
"""

        elif res.resource_type == "aws_ecs_task_definition":
            return f"""# Migrated from AWS ECS Fargate to Google Cloud Run (v2)
resource "google_cloud_run_v2_service" "{clean_name}" {{
  name     = "{clean_name.replace('_', '-')}"
  location = "{self.region}"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {{
    containers {{
      image = "gcr.io/{self.project_id}/{clean_name}:latest"
      resources {{
        limits = {{
          cpu    = "1000m"
          memory = "1024Mi"
        }}
      }}
      ports {{
        container_port = 8080
      }}
    }}
  }}

  depends_on = [google_project_service.enabled_apis]
}}
"""

        elif res.resource_type == "aws_db_instance":
            db_id = res.attributes.get("identifier", clean_name)
            engine = res.attributes.get("engine", "postgres")
            db_version = "POSTGRES_15" if "postgres" in engine else "MYSQL_8_0"
            return f"""# Migrated from AWS RDS to Google Cloud SQL
resource "google_sql_database_instance" "{clean_name}" {{
  name             = "{db_id}"
  database_version = "{db_version}"
  region           = "{self.region}"

  settings {{
    tier = "db-f1-micro"
    backup_configuration {{
      enabled = true
    }}
    ip_configuration {{
      ipv4_enabled = true
      require_ssl  = true
    }}
  }}

  deletion_protection = false
  depends_on          = [google_project_service.enabled_apis]
}}
"""

        elif res.resource_type == "aws_dynamodb_table":
            table_name = res.attributes.get("name", clean_name)
            return f"""# Migrated from AWS DynamoDB to Google Cloud Firestore (Datastore Mode)
resource "google_firestore_database" "{clean_name}" {{
  project     = "{self.project_id}"
  name        = "(default)"
  location_id = "{self.region}"
  type        = "DATASTORE_MODE"

  depends_on = [google_project_service.enabled_apis]
}}
"""

        else:
            mapping = get_service_mapping(res.resource_type)
            return f"""# Migrated from {res.resource_type} ({res.resource_name})
# Target GCP Resource: {mapping['gcp_resource']}
# Service: {mapping['gcp_service']}
# Architecture note: {mapping['rationale']}
"""

    def generate_report(self, resources: List[AWSResource], llm_insights: str = "") -> str:
        """Constructs a comprehensive Markdown migration report."""
        mapping_rows = []
        required_apis = set()

        for res in resources:
            mapping = get_service_mapping(res.resource_type)
            api = mapping.get("required_api")
            if api:
                required_apis.add(api)
            mapping_rows.append(
                f"| `{res.resource_type}` ({res.resource_name}) | **{mapping['gcp_service']}** (`{mapping['gcp_resource']}`) | {mapping['rationale']} |"
            )

        apis_command = " ".join(sorted(required_apis))

        report = f"""# AWS to Google Cloud Platform Migration Report

> Generated automatically by `aws-to-gcp-migrator`
> **Target GCP Project:** `{self.project_id}` | **Target Region:** `{self.region}`

---

## 1. Executive Summary

This report outlines the automated translation of your AWS infrastructure into modern, idiomatic Google Cloud Platform architecture. The target configuration leverages GCP-native serverless primitives, unified object storage, and managed IAM security.

### Architecture Resource Mapping
| AWS Resource | GCP Target Service | Rationale |
| :--- | :--- | :--- |
{chr(10).join(mapping_rows)}

---

## 2. Google Cloud Service Enablement

Before applying the generated Terraform, activate the required Google Cloud APIs:

```bash
gcloud config set project {self.project_id}
gcloud services enable {apis_command}
```

---

## 3. Cost & Free-Tier Optimization Benefits

Migrating to Google Cloud provides immediate free-tier advantages:
- **Cloud Functions (2nd Gen) & Cloud Run**: 2,000,000 free invocations and 360,000 GB-seconds per month.
- **Cloud Storage**: 5 GB free regional storage in US regions per month.
- **Cloud Pub/Sub**: First 10 GB of monthly throughput free of charge.
- **Network Egress**: 100 GB free internet egress per month from North American regions.

---

## 4. Security & IAM Posture Recommendations

1. **Uniform Bucket-Level Access**: Enabled by default on Google Cloud Storage buckets to eliminate risky object ACLs.
2. **Workload Identity Federation**: Replace static long-lived credentials by using GCP Workload Identity with GitHub Actions or AWS OIDC.
3. **Dedicated Service Accounts**: Each serverless workload (Cloud Functions / Cloud Run) uses an isolated service account adhering to the principle of least privilege.

---

## 5. Next Steps for Deployment

1. **Review Generated Terraform**:
   Inspect `main.tf` in the output directory.

2. **Authenticate with Google Cloud**:
   ```bash
   gcloud auth application-default login
   ```

3. **Initialize and Apply**:
   ```bash
   terraform init
   terraform plan -out=tfplan
   terraform apply tfplan
   ```
"""

        if llm_insights:
            report += f"""
---

## 6. AI Agent Synthesis & Deep-Dive Insights

{llm_insights}
"""

        return report
