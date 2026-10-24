"""
Generates idiomatic GCP Terraform configurations, Markdown reports, and rich interactive HTML dashboards.
"""

import json
from typing import List, Dict, Any, Optional
from .parser import AWSResource
from .mapper import get_service_mapping, get_gcp_region
from .topology_agent import TopologyGraph
from .finops_agent import FinOpsReport


# Deep architectural comparisons explaining "Why GCP over AWS"
COMPARISON_MATRIX: Dict[str, Dict[str, str]] = {
    "aws_ecs_task_definition": {
        "title": "AWS ECS Fargate ➔ Google Cloud Run (v2)",
        "aws_name": "AWS ECS Fargate",
        "gcp_name": "Google Cloud Run (v2)",
        "what_is_it": "Serverless container execution platform that runs OCI containers without managing virtual machines, clusters, or orchestrators.",
        "why_better": "AWS Fargate allocates dedicated CPU/memory per task with 1:1 request handling. Cloud Run supports multi-stream concurrency (up to 1,000 concurrent requests per instance), handling traffic spikes without spinning up dozens of containers. Sub-second cold starts drastically reduce latency compared to Fargate task provisioning.",
        "cost_advantage": "True scale-to-zero when idle (Fargate bills 24/7 for running tasks). Plus, GCP provides 2,000,000 free requests, 180,000 vCPU-seconds, and 360,000 GB-seconds free every month.",
        "migration_caveat": "Cloud Run throttles CPU when no active HTTP request is processing. For long-running background tasks, configure CPU always allocated or offload to Cloud Pub/Sub."
    },
    "aws_lambda_function": {
        "title": "AWS Lambda ➔ Cloud Functions (2nd Gen / Cloud Run)",
        "aws_name": "AWS Lambda",
        "gcp_name": "Google Cloud Functions (2nd Gen)",
        "what_is_it": "Event-driven serverless compute built on Knative and Cloud Run infrastructure.",
        "why_better": "Unlike Lambda's strict 1-invocation-per-instance constraint, Cloud Functions 2nd Gen supports request concurrency, larger instance sizes (up to 32GB RAM / 8 vCPUs), and execution timeouts up to 60 minutes (vs AWS Lambda's 15-minute hard limit).",
        "cost_advantage": "Concurrency allows a single active function instance to serve dozens of incoming requests simultaneously, slashing total billing duration. 2M free invocations/month included.",
        "migration_caveat": "Handlers use the Google Functions Framework (`functions_framework.http`) rather than the AWS Lambda handler signature."
    },
    "aws_vpc": {
        "title": "AWS Regional VPC ➔ Google Cloud Global VPC",
        "aws_name": "AWS Regional VPC",
        "gcp_name": "Google Cloud Global VPC",
        "what_is_it": "Global Software-Defined Network spanning all Google Cloud worldwide regions within a single routing and security boundary.",
        "why_better": "AWS VPCs are strictly tied to a single geographic region. Connecting multiple regions requires complex Inter-Region VPC Peering, Transit Gateways, and multiple NAT Gateways. A Google Cloud VPC is natively Global: subnets in Iowa, Frankfurt, and Tokyo communicate securely over Google's private fiber network without public traversal.",
        "cost_advantage": "Eliminates AWS Transit Gateway hourly fees ($36/mo per attachment) and redundant per-AZ NAT Gateway charges ($32.40/mo per AZ). A single Cloud NAT covers the entire region.",
        "migration_caveat": "Subnets must use non-overlapping CIDR blocks globally within the same VPC network."
    },
    "aws_sqs_queue": {
        "title": "AWS SQS ➔ Google Cloud Pub/Sub",
        "aws_name": "AWS SQS Queue",
        "gcp_name": "Google Cloud Pub/Sub",
        "what_is_it": "Globally distributed, low-latency asynchronous messaging and event ingestion backbone.",
        "why_better": "AWS SQS requires backend compute to constantly poll endpoints (`ReceiveMessage`), keeping instances running. Cloud Pub/Sub supports native Push Subscriptions that deliver messages via HTTPS webhooks directly into serverless Cloud Run endpoints, enabling 100% scale-to-zero when idle.",
        "cost_advantage": "First 10 GB of message throughput is free every month. Eliminates the cost of continuous compute polling loops.",
        "migration_caveat": "Pub/Sub delivers messages out-of-order by default. If strict sequence preservation is required, enable Pub/Sub Message Ordering Keys."
    },
    "aws_s3_bucket": {
        "title": "Amazon S3 ➔ Google Cloud Storage (GCS)",
        "aws_name": "Amazon S3",
        "gcp_name": "Google Cloud Storage",
        "what_is_it": "Highly scalable, unified object storage with automatic multi-region and dual-region replication.",
        "why_better": "GCS provides native Dual-Region replication (e.g., Iowa/South Carolina) with a zero-RTO 99.99% availability SLA without needing complex S3 Cross-Region Replication (CRR). Soft-delete protection is enabled by default to safeguard against ransomware or accidental deletion.",
        "cost_advantage": "5 GB free regional storage in US regions every month; lower per-operation request fees on the Google global backbone.",
        "migration_caveat": "Legacy S3 ACLs should be replaced with Uniform Bucket-Level Access (UBLA) for streamlined IAM compliance."
    },
    "aws_db_instance": {
        "title": "Amazon RDS ➔ Google Cloud SQL",
        "aws_name": "Amazon RDS",
        "gcp_name": "Google Cloud SQL",
        "what_is_it": "Fully managed relational database service supporting PostgreSQL, MySQL, and SQL Server.",
        "why_better": "Includes native Cloud SQL Auth Proxy for mutual TLS encryption and IAM-based database authentication without storing database passwords in code. Automatic storage scaling increases disk capacity without downtime.",
        "cost_advantage": "No IOPS surcharge for standard SSD storage. Committed Use Discounts (CUDs) offer up to 52% savings for 1-to-3-year commitments.",
        "migration_caveat": "Database cutovers require logical replication via GCP Database Migration Service (DMS) rather than direct snapshot restores."
    },
    "aws_iam_role": {
        "title": "AWS IAM Roles ➔ Google Service Accounts & Workload Identity",
        "aws_name": "AWS IAM Roles & Keys",
        "gcp_name": "GCP Service Accounts & Workload Identity",
        "what_is_it": "Identity and Access Management platform providing short-lived, keyless security tokens.",
        "why_better": "Replaces static long-lived AWS IAM access keys stored in CI/CD pipelines with Google Workload Identity Federation, federating identities directly with GitHub Actions, GitLab, or AWS using OIDC tokens.",
        "cost_advantage": "100% free native Google Cloud security capability.",
        "migration_caveat": "Permissions are organized into predefined and custom roles rather than AWS-style JSON inline policy documents."
    },
    "aws_security_group": {
        "title": "AWS Security Groups ➔ Google Cloud VPC Firewall Rules",
        "aws_name": "AWS Security Group",
        "gcp_name": "Cloud VPC Firewall Rules",
        "what_is_it": "Stateful network firewall filtering ingress and egress traffic at the virtual machine and container level.",
        "why_better": "Can be targeted using Service Accounts and network tags globally across all instances in the Global VPC, eliminating repetitive per-ENI security group assignments.",
        "cost_advantage": "Included free with Google Cloud VPC networking.",
        "migration_caveat": "Firewall rules operate on the VPC level rather than being attached directly to virtual network interfaces."
    }
}


class MigrationGenerator:
    """Generates GCP Terraform files, Markdown reports, and HTML presentation dashboards."""

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

        required_apis = set()
        for res in resources:
            mapping = get_service_mapping(res.resource_type)
            api = mapping.get("required_api")
            if api:
                required_apis.add(api)

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

        for res in resources:
            block = self._translate_resource(res)
            if block:
                tf_blocks.append(block)

        return "\n".join(tf_blocks)

    def _translate_resource(self, res: AWSResource) -> str:
        clean_name = res.resource_name.replace("-", "_")

        if res.resource_type == "aws_vpc":
            return f"""# Migrated from AWS Regional VPC to Google Cloud Global VPC
resource "google_compute_network" "{clean_name}" {{
  name                    = "{clean_name.replace('_', '-')}-vpc"
  auto_create_subnetworks = false
  description             = "Global VPC migrated from AWS VPC {clean_name}"

  depends_on = [google_project_service.enabled_apis]
}}
"""
        elif res.resource_type == "aws_subnet":
            cidr = res.attributes.get("cidr_block", "10.0.1.0/24")
            return f"""# Migrated from AWS Subnet to Google Cloud Subnetwork
resource "google_compute_subnetwork" "{clean_name}" {{
  name                     = "{clean_name.replace('_', '-')}-subnet"
  ip_cidr_range            = "{cidr}"
  region                   = "{self.region}"
  network                  = google_compute_network.production_vpc.id
  private_ip_google_access = true

  depends_on = [google_project_service.enabled_apis]
}}
"""
        elif res.resource_type == "aws_security_group":
            return f"""# Migrated from AWS Security Group to Google Cloud Firewall Rule
resource "google_compute_firewall" "{clean_name}" {{
  name    = "allow-{clean_name.replace('_', '-')}"
  network = google_compute_network.production_vpc.name

  allow {{
    protocol = "tcp"
    ports    = ["80", "443", "8080"]
  }}

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["{clean_name.replace('_', '-')}"]
}}
"""
        elif res.resource_type == "aws_s3_bucket":
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
  account_id   = "{clean_name[:28].replace('_', '-')}-sa"
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

    def generate_report(
        self,
        resources: List[AWSResource],
        topology: Optional[TopologyGraph] = None,
        finops: Optional[FinOpsReport] = None,
        llm_insights: str = ""
    ) -> str:
        """Constructs a comprehensive Markdown migration report with diagrams and FinOps data."""
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

        report_lines = [
            "# AWS to Google Cloud Platform Migration Report",
            "",
            "> Generated automatically by `aws-to-gcp-migrator` (Three-Agent Orchestration)",
            f"> **Target GCP Project:** `{self.project_id}` | **Target Region:** `{self.region}`",
            "",
            "---",
            "",
            "## 1. Executive Summary & Architecture Topology",
            "",
            "This report details the automated translation of your AWS infrastructure into modern, idiomatic Google Cloud Platform architecture.",
            ""
        ]

        if topology:
            report_lines.extend([
                "### AWS Source Topology",
                "```mermaid",
                topology.aws_mermaid,
                "```",
                "",
                "### Target GCP Modernized Topology",
                "```mermaid",
                topology.gcp_mermaid,
                "```",
                ""
            ])

        report_lines.extend([
            "### Architecture Resource Mapping",
            "| AWS Resource | GCP Target Service | Rationale |",
            "| :--- | :--- | :--- |",
            "\n".join(mapping_rows),
            "",
            "---",
            "",
            "## 2. FinOps Predictor: Total Cost of Ownership (TCO) Delta",
            ""
        ])

        if finops:
            report_lines.extend([
                f"- **Projected AWS Monthly Cost:** `${finops.total_aws_cost:.2f}`",
                f"- **Projected GCP Monthly Cost:** `${finops.total_gcp_cost:.2f}`",
                f"- **Monthly Net Savings:** `${finops.total_savings:.2f}` (**{finops.savings_percentage}% savings** on Google Cloud)",
                "",
                "| Service Category | AWS Resource | Est. AWS/mo | Est. GCP/mo | Net Savings | Free Tier Impact |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |"
            ])
            for item in finops.items:
                report_lines.append(
                    f"| {item.service_name} | `{item.aws_resource}` | ${item.aws_monthly_cost:.2f} | ${item.gcp_monthly_cost:.2f} | ${item.savings:.2f} | {item.free_tier_impact} |"
                )
            report_lines.append("")

        report_lines.extend([
            "---",
            "",
            "## 3. Google Cloud Service Enablement",
            "",
            "Before applying the generated Terraform, activate the required Google Cloud APIs:",
            "",
            "```bash",
            f"gcloud config set project {self.project_id}",
            f"gcloud services enable {apis_command}",
            "```",
            "",
            "---",
            "",
            "## 4. Security & IAM Posture Recommendations",
            "",
            "1. **Global VPC Architecture**: Single unified VPC spanning all Google regions without complex cross-region peering.",
            "2. **Uniform Bucket-Level Access**: Eliminates risky object-level ACLs across Cloud Storage buckets.",
            "3. **Workload Identity Federation**: Eliminates long-lived static keys; authenticates workloads via OIDC tokens.",
            "4. **Isolated Service Accounts**: Dedicated least-privilege service accounts for each serverless and containerized component.",
            "",
            "---",
            "",
            "## 5. Next Steps for Deployment",
            "",
            "1. **Review Generated Terraform**: Inspect `main.tf` in the output directory.",
            "2. **Authenticate with Google Cloud**:",
            "   ```bash",
            "   gcloud auth application-default login",
            "   ```",
            "3. **Initialize and Apply**:",
            "   ```bash",
            "   terraform init",
            "   terraform plan -out=tfplan",
            "   terraform apply tfplan",
            "   ```"
        ])

        if llm_insights:
            report_lines.extend([
                "",
                "---",
                "",
                "## 6. AI Agent Synthesis & Deep-Dive Insights",
                "",
                llm_insights
            ])

        return "\n".join(report_lines)

    def generate_dashboard_html(
        self,
        resources: List[AWSResource],
        topology: TopologyGraph,
        finops: FinOpsReport,
        llm_insights: str = ""
    ) -> str:
        """Constructs an interactive presentation dashboard with deep-dive comparison drawers and ROI calculator."""

        # Build comparison cards data
        comparison_cards_html = []
        seen_comparisons = set()

        for res in resources:
            comp = COMPARISON_MATRIX.get(res.resource_type)
            if comp and res.resource_type not in seen_comparisons:
                seen_comparisons.add(res.resource_type)
                comparison_cards_html.append(f"""
                <div class="decision-card" onclick="openDrawer('{res.resource_type}')">
                  <div class="decision-header">
                    <span class="decision-title">{comp['title']}</span>
                    <span class="badge-action">Explore Why ➔</span>
                  </div>
                  <div class="decision-body">
                    <p><strong>What is it?</strong> {comp['what_is_it'][:130]}...</p>
                    <div class="decision-highlight">
                      <strong>Key Advantage:</strong> {comp['why_better'][:140]}...
                    </div>
                  </div>
                </div>
                """)

        # Serialize comparisons for client-side JavaScript drawer
        comparisons_json = json.dumps(COMPARISON_MATRIX)

        # Build FinOps table rows
        table_rows = []
        for item in finops.items:
            table_rows.append(f"""
            <tr>
              <td><strong>{item.service_name}</strong></td>
              <td><code>{item.aws_resource}</code></td>
              <td>${item.aws_monthly_cost:.2f}</td>
              <td class="gcp-highlight">${item.gcp_monthly_cost:.2f}</td>
              <td class="savings-text">+${item.savings:.2f}</td>
              <td><span class="badge-free">{item.free_tier_impact}</span></td>
            </tr>
            """)

        # Format Gemini text for clean HTML rendering
        clean_insights = (
            llm_insights.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AWS to GCP Migration Command Center | GDG DevFest</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <script>mermaid.initialize({{ startOnLoad: true, theme: 'dark' }});</script>
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: #151d30;
      --card-hover: #1e2942;
      --border: #23304c;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #4285F4;
      --accent-green: #34A853;
      --accent-yellow: #FBBC05;
      --accent-red: #EA4335;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: var(--font);
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 0;
      line-height: 1.5;
    }}
    .container {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 32px 24px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--border);
      flex-wrap: wrap;
      gap: 16px;
    }}
    .logo-badge {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    h1 {{
      margin: 0;
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.5px;
    }}
    .badge {{
      background: rgba(66, 133, 244, 0.18);
      color: var(--accent);
      padding: 6px 14px;
      border-radius: 9999px;
      font-size: 13px;
      font-weight: 600;
      border: 1px solid rgba(66, 133, 244, 0.4);
    }}
    .badge-live {{
      background: rgba(52, 168, 83, 0.18);
      color: var(--accent-green);
      padding: 6px 14px;
      border-radius: 9999px;
      font-size: 13px;
      font-weight: 600;
      border: 1px solid rgba(52, 168, 83, 0.4);
    }}
    .tabs-nav {{
      display: flex;
      gap: 8px;
      margin: 28px 0 20px 0;
      border-bottom: 1px solid var(--border);
      padding-bottom: 12px;
      overflow-x: auto;
    }}
    .tab-btn {{
      background: transparent;
      border: none;
      color: var(--text-muted);
      padding: 10px 18px;
      font-size: 14px;
      font-weight: 600;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      gap: 8px;
      white-space: nowrap;
    }}
    .tab-btn:hover {{
      color: var(--text);
      background: var(--card-bg);
    }}
    .tab-btn.active {{
      background: var(--accent);
      color: #fff;
    }}
    .tab-content {{
      display: none;
      animation: fadeIn 0.25s ease;
    }}
    .tab-content.active {{
      display: block;
    }}
    @keyframes fadeIn {{
      from {{ opacity: 0; transform: translateY(4px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    .grid-kpi {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }}
    .kpi-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
    }}
    .kpi-label {{
      color: var(--text-muted);
      font-size: 13px;
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .kpi-val {{
      font-size: 30px;
      font-weight: 700;
      letter-spacing: -0.5px;
    }}
    .text-green {{ color: var(--accent-green); }}
    .text-blue {{ color: var(--accent); }}
    .text-yellow {{ color: var(--accent-yellow); }}
    
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 24px;
      margin-bottom: 24px;
    }}
    .card-title {{
      margin: 0 0 16px 0;
      font-size: 18px;
      font-weight: 600;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .decisions-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      gap: 18px;
    }}
    .decision-card {{
      background: #111827;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      cursor: pointer;
      transition: all 0.2s ease;
    }}
    .decision-card:hover {{
      background: var(--card-hover);
      border-color: var(--accent);
      transform: translateY(-2px);
    }}
    .decision-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;
    }}
    .decision-title {{
      font-weight: 700;
      font-size: 15px;
      color: #e2e8f0;
    }}
    .badge-action {{
      font-size: 11px;
      color: var(--accent);
      font-weight: 600;
      background: rgba(66, 133, 244, 0.15);
      padding: 3px 8px;
      border-radius: 4px;
    }}
    .decision-body p {{
      margin: 0 0 10px 0;
      font-size: 13px;
      color: var(--text-muted);
    }}
    .decision-highlight {{
      background: rgba(52, 168, 83, 0.1);
      border-left: 3px solid var(--accent-green);
      padding: 8px 12px;
      font-size: 12px;
      color: #86efac;
      border-radius: 0 6px 6px 0;
    }}
    .diagrams-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }}
    @media (max-width: 900px) {{
      .diagrams-grid {{ grid-template-columns: 1fr; }}
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      padding: 12px 14px;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }}
    th {{
      color: var(--text-muted);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 12px;
    }}
    .gcp-highlight {{
      color: var(--accent);
      font-weight: 600;
    }}
    .savings-text {{
      color: var(--accent-green);
      font-weight: 700;
    }}
    .badge-free {{
      background: rgba(52, 168, 83, 0.15);
      color: var(--accent-green);
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
    }}
    
    /* Interactive Drawer Modal */
    .drawer-overlay {{
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(4px);
      z-index: 1000;
      justify-content: flex-end;
    }}
    .drawer {{
      width: 100%;
      max-width: 600px;
      background: #111827;
      height: 100%;
      overflow-y: auto;
      padding: 32px;
      border-left: 1px solid var(--border);
      box-shadow: -10px 0 30px rgba(0,0,0,0.5);
      animation: slideIn 0.3s ease;
    }}
    @keyframes slideIn {{
      from {{ transform: translateX(100%); }}
      to {{ transform: translateX(0); }}
    }}
    .drawer-close {{
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 24px;
      cursor: pointer;
      float: right;
    }}
    .drawer-section {{
      margin-bottom: 24px;
    }}
    .drawer-section h3 {{
      font-size: 14px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--accent);
      margin: 0 0 8px 0;
    }}
    .drawer-section p {{
      margin: 0;
      font-size: 14px;
      color: #cbd5e1;
      line-height: 1.6;
    }}
    .box-green {{
      background: rgba(52, 168, 83, 0.1);
      border: 1px solid rgba(52, 168, 83, 0.3);
      padding: 16px;
      border-radius: 8px;
    }}
    .box-yellow {{
      background: rgba(251, 188, 5, 0.1);
      border: 1px solid rgba(251, 188, 5, 0.3);
      padding: 16px;
      border-radius: 8px;
    }}
    
    /* Interactive Simulator */
    .slider-group {{
      margin-bottom: 20px;
    }}
    .slider-header {{
      display: flex;
      justify-content: space-between;
      margin-bottom: 8px;
      font-size: 14px;
    }}
    input[type=range] {{
      width: 100%;
      accent-color: var(--accent-green);
    }}
    pre {{
      background: #090d16;
      border: 1px solid var(--border);
      padding: 16px;
      border-radius: 8px;
      overflow-x: auto;
      font-size: 13px;
      color: #7dd3fc;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="logo-badge">
        <h1>AWS to GCP Migration Command Center</h1>
        <span class="badge">GDG DevFest 2026</span>
        <span class="badge-live">Live Gemini 3.8 Active</span>
      </div>
      <div>
        <span style="color: var(--text-muted); font-size: 13px;">Target Project: <strong>{self.project_id}</strong> | Region: <strong>{self.region}</strong></span>
      </div>
    </header>

    <div class="tabs-nav">
      <button class="tab-btn active" onclick="switchTab('tab-why')">🔍 Why We Chose This (Architecture Decisions)</button>
      <button class="tab-btn" onclick="switchTab('tab-topology')">📊 Architecture Topology</button>
      <button class="tab-btn" onclick="switchTab('tab-finops')">💰 FinOps & ROI Simulator</button>
      <button class="tab-btn" onclick="switchTab('tab-gemini')">🤖 Live Gemini Synthesis</button>
    </div>

    <!-- TAB 1: WHY WE CHOSE THIS -->
    <div id="tab-why" class="tab-content active">
      <div class="grid-kpi">
        <div class="kpi-card">
          <div class="kpi-label">Projected Monthly Savings</div>
          <div class="kpi-val text-green">${finops.total_savings:.2f} <span style="font-size: 16px;">({finops.savings_percentage}%)</span></div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">AWS Baseline Run-Rate</div>
          <div class="kpi-val text-yellow">${finops.total_aws_cost:.2f}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">GCP Target Run-Rate</div>
          <div class="kpi-val text-blue">${finops.total_gcp_cost:.2f}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Mapped Cloud Primitives</div>
          <div class="kpi-val">{len(resources)} Units</div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">
          <span>Architectural Decision Records (Click any card for deep comparison)</span>
          <span style="font-size: 12px; color: var(--text-muted); font-weight: normal;">Interactive Decision Matrix</span>
        </div>
        <div class="decisions-grid">
          {''.join(comparison_cards_html)}
        </div>
      </div>
    </div>

    <!-- TAB 2: TOPOLOGY -->
    <div id="tab-topology" class="tab-content">
      <div class="card">
        <div class="card-title">
          <span>Infrastructure Topology Transpilation</span>
          <span style="font-size: 12px; color: var(--accent);">Rendered with Mermaid.js</span>
        </div>
        <div class="diagrams-grid">
          <div>
            <h4 style="color: var(--text-muted); margin: 0 0 12px 0;">AWS Source Topology</h4>
            <div class="mermaid">
{topology.aws_mermaid}
            </div>
          </div>
          <div>
            <h4 style="color: var(--accent); margin: 0 0 12px 0;">Google Cloud Modernized Topology</h4>
            <div class="mermaid">
{topology.gcp_mermaid}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 3: FINOPS & SIMULATOR -->
    <div id="tab-finops" class="tab-content">
      <div class="card">
        <div class="card-title">
          <span>Interactive Cost Scaling Simulator</span>
          <span style="font-size: 12px; color: var(--accent-green);">Real-time TCO Calculator</span>
        </div>
        <p style="color: var(--text-muted); font-size: 14px; margin-top: 0;">Adjust monthly workload volume to simulate projected savings at enterprise scale.</p>
        
        <div class="slider-group">
          <div class="slider-header">
            <span>Monthly API Requests (Millions): <strong id="val-requests">10M</strong></span>
            <span id="sim-concurrency-note" style="color: var(--accent);">Cloud Run: 1000 requests/instance concurrency</span>
          </div>
          <input type="range" id="slider-requests" min="1" max="100" value="10" oninput="updateSim()">
        </div>

        <div class="grid-kpi" style="margin-top: 24px;">
          <div class="kpi-card">
            <div class="kpi-label">Simulated AWS Run-Rate</div>
            <div class="kpi-val text-yellow" id="sim-aws">$147.50</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">Simulated GCP Run-Rate</div>
            <div class="kpi-val text-blue" id="sim-gcp">$79.40</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">Projected Net Monthly Savings</div>
            <div class="kpi-val text-green" id="sim-savings">$68.10 (46.2%)</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Service-by-Service Cost Breakdown & Free Tier Impact</div>
        <table>
          <thead>
            <tr>
              <th>Service</th>
              <th>Source AWS Resource</th>
              <th>AWS Baseline</th>
              <th>GCP Target</th>
              <th>Net Savings</th>
              <th>Free Tier Allowance</th>
            </tr>
          </thead>
          <tbody>
            {''.join(table_rows)}
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 4: GEMINI SYNTHESIS -->
    <div id="tab-gemini" class="tab-content">
      <div class="card">
        <div class="card-title">Live Google Gemini 3.8 Flash Architectural Synthesis</div>
        <div style="line-height: 1.7; color: #cbd5e1; font-size: 14px;">
          {clean_insights}
        </div>
      </div>
    </div>
  </div>

  <!-- INTERACTIVE DRAWER FOR "WHY WE CHOSE THIS" -->
  <div id="drawer-overlay" class="drawer-overlay" onclick="closeDrawer(event)">
    <div class="drawer" onclick="event.stopPropagation()">
      <button class="drawer-close" onclick="closeDrawer()">&times;</button>
      <h2 id="drawer-title" style="margin: 0 0 20px 0; font-size: 20px; color: #fff;"></h2>
      
      <div class="drawer-section">
        <h3>What is it?</h3>
        <p id="drawer-what"></p>
      </div>

      <div class="drawer-section box-green">
        <h3 style="color: var(--accent-green);">Why is it better on Google Cloud?</h3>
        <p id="drawer-better"></p>
      </div>

      <div class="drawer-section" style="margin-top: 20px;">
        <h3>Why is it cost-effective?</h3>
        <p id="drawer-cost"></p>
      </div>

      <div class="drawer-section box-yellow">
        <h3 style="color: var(--accent-yellow);">Migration Gotcha / Breaking Change to Watch:</h3>
        <p id="drawer-gotcha"></p>
      </div>
    </div>
  </div>

  <script>
    const comparisons = {comparisons_json};

    function switchTab(tabId) {{
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
      document.getElementById(tabId).classList.add('active');
      event.target.classList.add('active');
    }}

    function openDrawer(resType) {{
      const comp = comparisons[resType];
      if (!comp) return;

      document.getElementById('drawer-title').innerText = comp.title;
      document.getElementById('drawer-what').innerText = comp.what_is_it;
      document.getElementById('drawer-better').innerText = comp.why_better;
      document.getElementById('drawer-cost').innerText = comp.cost_advantage;
      document.getElementById('drawer-gotcha').innerText = comp.migration_caveat;

      document.getElementById('drawer-overlay').style.display = 'flex';
    }}

    function closeDrawer(e) {{
      document.getElementById('drawer-overlay').style.display = 'none';
    }}

    function updateSim() {{
      const reqs = parseFloat(document.getElementById('slider-requests').value);
      document.getElementById('val-requests').innerText = reqs + 'M';

      // Base costs from 10M requests
      const baseAWS = 147.50;
      const baseGCP = 79.40;

      // Scaling factor: Fargate scales linearly; Cloud Run scales with concurrency
      const scaledAWS = (baseAWS * (reqs / 10)).toFixed(2);
      const scaledGCP = (baseGCP * (1 + (reqs - 10) * 0.05)).toFixed(2);
      const savings = (scaledAWS - scaledGCP).toFixed(2);
      const pct = ((savings / scaledAWS) * 100).toFixed(1);

      document.getElementById('sim-aws').innerText = '$' + scaledAWS;
      document.getElementById('sim-gcp').innerText = '$' + scaledGCP;
      document.getElementById('sim-savings').innerText = '$' + savings + ' (' + pct + '%)';
    }}
  </script>
</body>
</html>
"""
        return html
