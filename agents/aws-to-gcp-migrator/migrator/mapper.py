"""
AWS to Google Cloud Service & Architecture Mapping Knowledge Base
"""

from typing import Dict, Any, List

# Region mappings
REGION_MAP = {
    "us-east-1": "us-east1",
    "us-east-2": "us-east4",
    "us-west-1": "us-west1",
    "us-west-2": "us-west2",
    "eu-west-1": "europe-west1",
    "eu-central-1": "europe-west3",
    "ap-south-1": "asia-south1",
    "ap-southeast-1": "asia-southeast1",
    "ap-northeast-1": "asia-northeast1",
}

# AWS to GCP Resource and Architecture Mapping Catalog
SERVICE_CATALOG: Dict[str, Dict[str, Any]] = {
    "aws_vpc": {
        "gcp_service": "Virtual Private Cloud (Global VPC)",
        "gcp_resource": "google_compute_network",
        "required_api": "compute.googleapis.com",
        "rationale": "GCP VPC is natively Global rather than Regional. A single VPC spans all Google regions worldwide without needing complex inter-region VPC peering.",
        "cost_benefit": "Zero inter-region VPC peering overhead on Google's private fiber network.",
        "security_note": "Centralized global firewall policies and Cloud Armor integration.",
    },
    "aws_subnet": {
        "gcp_service": "Cloud Subnetwork",
        "gcp_resource": "google_compute_subnetwork",
        "required_api": "compute.googleapis.com",
        "rationale": "Regional subnets within the Global VPC with Private Google Access enabled by default.",
        "cost_benefit": "Cross-subnet traffic flows over private Google backbone avoiding public internet charges.",
        "security_note": "Enforce Private Google Access to reach APIs without public IPs.",
    },
    "aws_security_group": {
        "gcp_service": "Cloud Firewall Rules",
        "gcp_resource": "google_compute_firewall",
        "required_api": "compute.googleapis.com",
        "rationale": "Stateful firewall rules applied globally across instances and clusters using service accounts or network tags.",
        "cost_benefit": "Included free with Google Cloud VPC networking.",
        "security_note": "Deny by default ingress; allow egress with hierarchical firewall policies.",
    },
    "aws_s3_bucket": {
        "gcp_service": "Cloud Storage",
        "gcp_resource": "google_storage_bucket",
        "required_api": "storage.googleapis.com",
        "rationale": "Google Cloud Storage offers unified bucket APIs, automatic dual-region replication, and native soft-delete protection.",
        "cost_benefit": "5 GB free tier storage per month in US regions; lower per-operation egress costs on Google backbone.",
        "security_note": "Uniform bucket-level access recommended to eliminate legacy ACL vulnerabilities.",
    },
    "aws_lambda_function": {
        "gcp_service": "Cloud Functions (2nd Gen) / Cloud Run",
        "gcp_resource": "google_cloudfunctions2_function",
        "required_api": "cloudfunctions.googleapis.com",
        "rationale": "Cloud Functions 2nd Gen is built on Google Cloud Run and Knative, allowing longer timeouts (up to 60m) and concurrency up to 1000 requests/instance.",
        "cost_benefit": "2 million free invocations per month, 180,000 vCPU-seconds and 360,000 GB-seconds free monthly.",
        "security_note": "Integrated with Google Cloud Armor and Workload Identity without static keys.",
    },
    "aws_sqs_queue": {
        "gcp_service": "Cloud Pub/Sub",
        "gcp_resource": "google_pubsub_topic",
        "required_api": "pubsub.googleapis.com",
        "rationale": "Cloud Pub/Sub provides native global routing without region peering, automatic horizontal scaling, and dead-letter topics.",
        "cost_benefit": "First 10 GB of message throughput free every month.",
        "security_note": "Encryption at rest by default using Google-managed or customer-managed CMEK.",
    },
    "aws_iam_role": {
        "gcp_service": "Cloud IAM Service Account",
        "gcp_resource": "google_service_account",
        "required_api": "iam.googleapis.com",
        "rationale": "GCP Service Accounts use granular IAM roles (predefined or custom) bound via Google IAM Policy instead of complex AWS inline JSON policies.",
        "cost_benefit": "Free native IAM service.",
        "security_note": "Migrate to Workload Identity Federation to eliminate long-lived service account keys completely.",
    },
    "aws_ecs_task_definition": {
        "gcp_service": "Cloud Run (v2)",
        "gcp_resource": "google_cloud_run_v2_service",
        "required_api": "run.googleapis.com",
        "rationale": "Cloud Run provides serverless container execution with auto-scaling to zero, request concurrency, and built-in HTTPS endpoints.",
        "cost_benefit": "Pay only for CPU during active request processing (scale to zero when idle).",
        "security_note": "Automatic TLS certificates and optional private VPC egress connector.",
    },
    "aws_db_instance": {
        "gcp_service": "Cloud SQL",
        "gcp_resource": "google_sql_database_instance",
        "required_api": "sqladmin.googleapis.com",
        "rationale": "Cloud SQL offers fully managed PostgreSQL, MySQL, and SQL Server with automated maintenance, point-in-time recovery, and high availability.",
        "cost_benefit": "Committed use discounts up to 52%; automatic storage scaling.",
        "security_note": "Enforce Private IP / Cloud SQL Auth Proxy; SSL/TLS enforced by default.",
    },
    "aws_dynamodb_table": {
        "gcp_service": "Firestore (Datastore Mode)",
        "gcp_resource": "google_firestore_database",
        "required_api": "firestore.googleapis.com",
        "rationale": "Cloud Firestore offers multi-region active-active replication, strongly consistent queries, and serverless auto-scaling.",
        "cost_benefit": "1 GB storage, 50,000 reads, 20,000 writes free per day.",
        "security_note": "Integrated with Firebase Security Rules and GCP IAM.",
    },
}


def get_gcp_region(aws_region: str, default: str = "us-central1") -> str:
    """Translates AWS region identifier to GCP region."""
    return REGION_MAP.get(aws_region.lower().strip(), default)


def get_service_mapping(aws_resource_type: str) -> Dict[str, Any]:
    """Retrieves GCP service mapping details or defaults."""
    return SERVICE_CATALOG.get(
        aws_resource_type,
        {
            "gcp_service": "Google Cloud Equivalent",
            "gcp_resource": f"google_{aws_resource_type.replace('aws_', '')}",
            "required_api": "compute.googleapis.com",
            "rationale": "Standard cloud resource translation to Google Cloud Platform.",
            "cost_benefit": "Check Google Cloud Pricing Calculator for free tier eligibility.",
            "security_note": "Apply principle of least privilege using Google Cloud IAM.",
        }
    )
