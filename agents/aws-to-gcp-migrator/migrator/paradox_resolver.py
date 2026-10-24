"""
Automatic Architecture Paradox Resolver
Detects AWS-specific architectural anti-patterns and paradoxes,
resolving them with idiomatic Google Cloud Platform native solutions.
"""

from dataclasses import dataclass
from typing import List, Dict, Any
from .parser import AWSResource


@dataclass
class ResolvedParadox:
    paradox_id: str
    title: str
    aws_paradox: str
    gcp_resolution: str
    finops_impact: str
    architectural_verdict: str


class ArchitectureParadoxResolver:
    """Detects and resolves cross-cloud architectural paradoxes."""

    PARADOX_DEFINITIONS = [
        {
            "id": "regional_vpc_sprawl",
            "trigger_types": ["aws_vpc", "aws_subnet"],
            "title": "The Regional VPC Sprawl Paradox",
            "aws_paradox": "Multi-region workloads in AWS require deploying isolated regional VPCs interconnected by complex AWS Transit Gateways ($36/mo/attachment) and Inter-Region VPC Peering with per-GB transit surcharges.",
            "gcp_resolution": "Consolidated into a single Google Cloud Global VPC. Subnets across continents (Iowa, Frankfurt, Tokyo) communicate natively over Google's private global fiber network without peering appliances or transit gateways.",
            "finops_impact": "Eliminates AWS Transit Gateway hourly fees (~$72/mo for dual-region) and per-GB cross-peering transit tolls.",
            "architectural_verdict": "Transpiled to unified `google_compute_network` with Global routing mode."
        },
        {
            "id": "lambda_concurrency_starvation",
            "trigger_types": ["aws_lambda_function"],
            "title": "The Lambda Concurrency Bottleneck Paradox",
            "aws_paradox": "AWS Lambda enforces a strict 1-invocation-per-container execution model. Under a sudden burst of 500 concurrent requests, AWS spins up 500 separate container instances, triggering cold-start storms and massive container churn.",
            "gcp_resolution": "Migrated to Google Cloud Run (v2) with multi-stream request concurrency configured (up to 1,000 concurrent requests per instance). A burst of 500 requests is efficiently processed by 1–2 instances.",
            "finops_impact": "Reduces active container instance count by up to 85%, dramatically lowering total billed vCPU and memory seconds.",
            "architectural_verdict": "Transpiled to `google_cloud_run_v2_service` with auto-concurrency enabled."
        },
        {
            "id": "s3_crr_replication_tax",
            "trigger_types": ["aws_s3_bucket"],
            "title": "The S3 Cross-Region Replication (CRR) Tax Paradox",
            "aws_paradox": "Achieving multi-region disaster recovery in AWS requires creating and configuring two distinct S3 buckets, managing continuous asynchronous Cross-Region Replication (CRR), and paying duplicate storage and replication API fees.",
            "gcp_resolution": "Replaced with a single Google Cloud Storage Dual-Region or Multi-Region bucket (e.g., `nam4` Iowa/South Carolina) featuring active-active 99.99% availability and automatic failover under a single global namespace.",
            "finops_impact": "Cuts bucket administration overhead in half and eliminates asynchronous cross-bucket copy charges.",
            "architectural_verdict": "Transpiled to `google_storage_bucket` with uniform dual-region replication."
        },
        {
            "id": "sqs_long_polling_worker_waste",
            "trigger_types": ["aws_sqs_queue"],
            "title": "The SQS Worker Polling Waste Paradox",
            "aws_paradox": "AWS SQS requires dedicated background worker compute (EC2 or Fargate) to continuously run HTTP `ReceiveMessage` long-polling loops, burning billable CPU cycles even when queues are empty.",
            "gcp_resolution": "Migrated to Google Cloud Pub/Sub with Push Subscriptions that deliver webhook payloads directly into serverless Cloud Run endpoints, allowing worker compute to scale down to absolute zero when idle.",
            "finops_impact": "Completely eliminates 24/7 idle worker container billing.",
            "architectural_verdict": "Transpiled to `google_pubsub_topic` with HTTPS push subscription."
        }
    ]

    def resolve_paradoxes(self, resources: List[AWSResource]) -> List[ResolvedParadox]:
        detected_types = {r.resource_type for r in resources}
        resolved: List[ResolvedParadox] = []

        for p in self.PARADOX_DEFINITIONS:
            if any(t in detected_types for t in p["trigger_types"]):
                resolved.append(ResolvedParadox(
                    paradox_id=p["id"],
                    title=p["title"],
                    aws_paradox=p["aws_paradox"],
                    gcp_resolution=p["gcp_resolution"],
                    finops_impact=p["finops_impact"],
                    architectural_verdict=p["architectural_verdict"]
                ))

        return resolved
