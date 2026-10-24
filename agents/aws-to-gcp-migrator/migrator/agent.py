"""
AI Migration Agent reasoning loop using Google Gemini API or Offline Rule Engine.
"""

import os
import json
from typing import List, Optional
from .parser import AWSResource
from .mapper import get_service_mapping


class MigrationAgent:
    """Agent that synthesizes cross-cloud architecture migrations."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
        mock_mode: bool = False
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = model_name or os.getenv("MODEL_NAME", "gemini-2.5-flash")
        self.mock_mode = mock_mode or not bool(self.api_key)

    def analyze_migration(
        self,
        resources: List[AWSResource],
        raw_code: str,
        target_project: str,
        target_region: str
    ) -> str:
        """
        Analyzes the AWS architecture and generates deep migration insights.
        Uses Gemini if configured, otherwise falls back to the high-fidelity offline engine.
        """
        if self.mock_mode or not self.api_key:
            return self._offline_analysis(resources, target_project, target_region)

        return self._llm_analysis(resources, raw_code, target_project, target_region)

    def _offline_analysis(
        self,
        resources: List[AWSResource],
        target_project: str,
        target_region: str
    ) -> str:
        """High-fidelity offline rule engine analysis."""
        lines = [
            "### Automated Cloud Architecture Insights (Rule-Based Engine)",
            "",
            f"- **Target Region:** `{target_region}`",
            f"- **Target Project:** `{target_project}`",
            f"- **Total AWS Resources Detected:** {len(resources)}",
            "",
            "#### Architectural Modernization Recommendations:",
        ]

        has_lambda = any(r.resource_type == "aws_lambda_function" for r in resources)
        has_s3 = any(r.resource_type == "aws_s3_bucket" for r in resources)
        has_sqs = any(r.resource_type == "aws_sqs_queue" for r in resources)
        has_ecs = any(r.resource_type == "aws_ecs_task_definition" for r in resources)
        has_rds = any(r.resource_type == "aws_db_instance" for r in resources)

        if has_lambda:
            lines.extend([
                "1. **Serverless Compute Modernization:**",
                "   - Migrated from AWS Lambda to **Google Cloud Functions 2nd Gen** (backed by Cloud Run).",
                "   - *Concurrency advantage:* Unlike AWS Lambda's 1-request-per-instance model, Cloud Run instances can serve up to 1000 concurrent requests, drastically lowering cold-start latency and compute costs.",
                "   - *Networking:* Cloud Functions 2nd Gen can be attached directly to Serverless VPC Access for secure communication with private Cloud SQL or Memorystore instances."
            ])

        if has_s3:
            lines.extend([
                "2. **Storage Modernization:**",
                "   - Migrated from Amazon S3 to **Google Cloud Storage (GCS)**.",
                "   - *Access Control:* Switched to **Uniform Bucket-Level Access (UBLA)**. This eliminates legacy object-level ACL inconsistencies.",
                "   - *Data protection:* GCS provides automatic soft-delete protection for 7 days by default to protect against accidental object deletion."
            ])

        if has_sqs:
            lines.extend([
                "3. **Messaging & Event-Driven Architecture:**",
                "   - Migrated from Amazon SQS to **Google Cloud Pub/Sub**.",
                "   - *Global scope:* Cloud Pub/Sub topics are globally available without needing cross-region VPC peering.",
                "   - *Dead-letter handling:* Pub/Sub natively supports dead-letter queues with configurable max delivery attempts."
            ])

        if has_ecs:
            lines.extend([
                "4. **Containerized Workloads:**",
                "   - Migrated from AWS ECS Fargate to **Google Cloud Run (v2)**.",
                "   - *Zero-scaling:* Automatically scales down to 0 instances when idle, saving significant compute costs compared to fixed Fargate tasks.",
                "   - *TLS:* Includes out-of-the-box managed TLS certificates and URL provisioning."
            ])

        if has_rds:
            lines.extend([
                "5. **Managed Relational Database:**",
                "   - Migrated from Amazon RDS to **Google Cloud SQL**.",
                "   - *Security:* Recommended to deploy the **Cloud SQL Auth Proxy** in client containers to avoid exposing public database IPs.",
                "   - *Backups:* Enabled automated daily backups and binary logging for point-in-time recovery."
            ])

        lines.extend([
            "",
            "#### Security & IAM Hardening Checklist:",
            "- [ ] Replace any static AWS IAM access keys with Google Cloud **Workload Identity Federation**.",
            "- [ ] Ensure each Cloud Function / Cloud Run service has its own dedicated Service Account with minimum required predefined IAM roles.",
            "- [ ] Enforce organizational policy constraints (e.g., `constraints/gcp.resourceLocations` set to your approved regions)."
        ])

        return "\n".join(lines)

    def _llm_analysis(
        self,
        resources: List[AWSResource],
        raw_code: str,
        target_project: str,
        target_region: str
    ) -> str:
        """Invokes Gemini API via google-genai SDK for deep reasoning."""
        prompt = f"""You are a Principal Cloud Solutions Architect specializing in migrating enterprise workloads from Amazon Web Services (AWS) to Google Cloud Platform (GCP).

Analyze the following AWS Terraform code and infrastructure resources.
Provide a high-level architectural migration critique, highlighting:
1. Architectural enhancements available in GCP (e.g., Cloud Run concurrency vs AWS Lambda single concurrency, Cloud Storage global edge vs S3, Pub/Sub global messaging).
2. Cost optimization and GCP Free Tier leverage.
3. IAM security posture improvements (Workload Identity, least-privilege service accounts).
4. Potential migration caveats or breaking changes to watch out for.

Target GCP Project: {target_project}
Target GCP Region: {target_region}

Detected AWS Resources:
{[f"{r.resource_type} ({r.resource_name})" for r in resources]}

AWS Terraform Source:
```hcl
{raw_code[:3000]}
```

Provide your architectural synthesis in structured Markdown format.
"""

        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            if response and response.text:
                return response.text
        except Exception as e:
            # Fallback to offline analysis if API call fails or quota exceeded
            offline = self._offline_analysis(resources, target_project, target_region)
            return f"*(Notice: Gemini API call returned: {str(e)}. Displaying verified offline analysis engine output.)*\n\n{offline}"

        return self._offline_analysis(resources, target_project, target_region)
