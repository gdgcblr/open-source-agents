"""
Generates idiomatic GCP Terraform configurations, Markdown reports, and interactive HTML dashboards.
"""

from typing import List, Dict, Any, Optional
from .parser import AWSResource
from .mapper import get_service_mapping, get_gcp_region
from .topology_agent import TopologyGraph
from .finops_agent import FinOpsReport


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
  network                  = google_compute_network.main_vpc.id
  private_ip_google_access = true

  depends_on = [google_project_service.enabled_apis]
}}
"""

        elif res.resource_type == "aws_security_group":
            return f"""# Migrated from AWS Security Group to Google Cloud Firewall Rule
resource "google_compute_firewall" "{clean_name}" {{
  name    = "allow-{clean_name.replace('_', '-')}"
  network = google_compute_network.main_vpc.name

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
        """Constructs an interactive, visually impressive HTML dashboard for live hackathon demos."""
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

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AWS to GCP Migration Agent - GDG DevFest</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <script>mermaid.initialize({{ startOnLoad: true, theme: 'dark' }});</script>
  <style>
    :root {{
      --bg: #0f172a;
      --card-bg: #1e293b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #4285F4;
      --accent-green: #34A853;
      --accent-yellow: #FBBC05;
      --accent-red: #EA4335;
      --border: #334155;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 24px;
    }}
    .container {{
      max-width: 1200px;
      margin: 0 auto;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--border);
    }}
    .title-group h1 {{
      margin: 0;
      font-size: 26px;
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .badge {{
      background: rgba(66, 133, 244, 0.2);
      color: var(--accent);
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
    }}
    .grid-kpi {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin: 24px 0;
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
      margin-bottom: 8px;
    }}
    .kpi-val {{
      font-size: 28px;
      font-weight: 700;
    }}
    .text-green {{ color: var(--accent-green); }}
    .text-blue {{ color: var(--accent); }}
    .text-yellow {{ color: var(--accent-yellow); }}

    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 24px;
    }}
    h2 {{
      margin-top: 0;
      font-size: 18px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .diagrams-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }}
    @media (max-width: 800px) {{
      .diagrams-grid {{ grid-template-columns: 1fr; }}
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      padding: 12px;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }}
    th {{
      color: var(--text-muted);
      font-weight: 600;
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
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
    }}
    pre {{
      background: #0b1120;
      padding: 16px;
      border-radius: 8px;
      overflow-x: auto;
      font-size: 13px;
      color: #38bdf8;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="title-group">
        <h1>AWS to GCP Migration Agent</h1>
        <span class="badge">GDG DevFest 2026 Edition</span>
      </div>
      <div>
        <span style="color: var(--text-muted); font-size: 13px;">Target Project: <strong>{self.project_id}</strong> ({self.region})</span>
      </div>
    </header>

    <div class="grid-kpi">
      <div class="kpi-card">
        <div class="kpi-label">Projected Monthly Savings</div>
        <div class="kpi-val text-green">${finops.total_savings:.2f} <span style="font-size: 16px;">({finops.savings_percentage}%)</span></div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">AWS Monthly Baseline</div>
        <div class="kpi-val text-yellow">${finops.total_aws_cost:.2f}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">GCP Target Monthly</div>
        <div class="kpi-val text-blue">${finops.total_gcp_cost:.2f}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Migrated Resources</div>
        <div class="kpi-val">{len(resources)} Units</div>
      </div>
    </div>

    <div class="card">
      <h2>Architecture Topology Transpilation</h2>
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

    <div class="card">
      <h2>FinOps TCO & Free Tier Optimization Delta</h2>
      <table>
        <thead>
          <tr>
            <th>Service</th>
            <th>Source AWS Resource</th>
            <th>AWS Est.</th>
            <th>GCP Est.</th>
            <th>Net Savings</th>
            <th>Free Tier Impact</th>
          </tr>
        </thead>
        <tbody>
          {''.join(table_rows)}
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2>AI Architecture Insights & Modernization Critique</h2>
      <div style="line-height: 1.6; color: #cbd5e1;">
        {llm_insights.replace(chr(10), '<br/>')}
      </div>
    </div>
  </div>
</body>
</html>
"""
        return html
