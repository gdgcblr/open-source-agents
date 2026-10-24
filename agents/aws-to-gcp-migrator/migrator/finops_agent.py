"""
Agent 3: The FinOps Predictor
Calculates AWS vs GCP Total Cost of Ownership (TCO), projected monthly savings,
and Cross-Cloud Network Gravity / AWS Data Egress Toll.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from .parser import AWSResource


@dataclass
class ServiceCostItem:
    service_name: str
    aws_resource: str
    gcp_resource: str
    aws_monthly_cost: float
    gcp_monthly_cost: float
    savings: float
    free_tier_impact: str


@dataclass
class NetworkGravityReport:
    data_volume_gb: float
    aws_egress_rate_per_gb: float
    aws_exit_toll: float
    gcp_ingress_cost: float
    amortization_days: float
    gcp_tooling: str


@dataclass
class FinOpsReport:
    items: List[ServiceCostItem]
    total_aws_cost: float
    total_gcp_cost: float
    total_savings: float
    savings_percentage: float
    network_gravity: NetworkGravityReport = field(default_factory=lambda: NetworkGravityReport(
        data_volume_gb=500.0,
        aws_egress_rate_per_gb=0.09,
        aws_exit_toll=45.0,
        gcp_ingress_cost=0.0,
        amortization_days=19.8,
        gcp_tooling="Google Cloud Storage Transfer Service (100% Free Ingress & Zero Transfer Software Markup)"
    ))


class FinOpsPredictorAgent:
    """Agent that projects Total Cost of Ownership (TCO), GCP savings deltas, and egress gravity tolls."""

    COST_CATALOG = {
        "aws_lambda_function": {
            "name": "Serverless Compute",
            "aws_cost": 48.00,
            "gcp_cost": 16.00,
            "free_tier": "2M invocations and 360,000 GB-seconds free monthly",
        },
        "aws_s3_bucket": {
            "name": "Object Storage (500 GB)",
            "aws_cost": 11.50,
            "gcp_cost": 9.90,
            "free_tier": "5 GB free regional storage every month",
        },
        "aws_sqs_queue": {
            "name": "Message Queuing (20M msgs)",
            "aws_cost": 8.00,
            "gcp_cost": 2.50,
            "free_tier": "First 10 GB message throughput free every month",
        },
        "aws_ecs_task_definition": {
            "name": "Container Workload (Fargate vs Cloud Run)",
            "aws_cost": 54.00,
            "gcp_cost": 18.00,
            "free_tier": "180,000 vCPU-seconds and 360,000 GB-seconds free monthly",
        },
        "aws_db_instance": {
            "name": "Managed Relational Database",
            "aws_cost": 34.00,
            "gcp_cost": 21.00,
            "free_tier": "Automated daily backups included without IOPS surcharge",
        },
        "aws_dynamodb_table": {
            "name": "NoSQL Database",
            "aws_cost": 15.00,
            "gcp_cost": 4.00,
            "free_tier": "50,000 reads and 20,000 writes free daily",
        },
        "aws_iam_role": {
            "name": "IAM & Access Management",
            "aws_cost": 0.00,
            "gcp_cost": 0.00,
            "free_tier": "Native IAM & Workload Identity Federation 100% free",
        },
    }

    def predict_tco(self, resources: List[AWSResource], estimated_data_gb: float = 500.0) -> FinOpsReport:
        items: List[ServiceCostItem] = []
        total_aws = 0.0
        total_gcp = 0.0

        for res in resources:
            model = self.COST_CATALOG.get(res.resource_type)
            if not model:
                aws_c = 10.00
                gcp_c = 7.00
                ft = "Eligible for Google Cloud Free Tier"
                name = res.resource_type
            else:
                aws_c = model["aws_cost"]
                gcp_c = model["gcp_cost"]
                ft = model["free_tier"]
                name = model["name"]

            savings = max(0.0, aws_c - gcp_c)
            total_aws += aws_c
            total_gcp += gcp_c

            items.append(ServiceCostItem(
                service_name=name,
                aws_resource=f"{res.resource_type} ({res.resource_name})",
                gcp_resource="GCP Equivalent",
                aws_monthly_cost=aws_c,
                gcp_monthly_cost=gcp_c,
                savings=savings,
                free_tier_impact=ft
            ))

        total_savings = max(0.0, total_aws - total_gcp)
        savings_pct = (total_savings / total_aws * 100.0) if total_aws > 0 else 0.0

        # Calculate Cross-Cloud Network Gravity
        aws_egress_rate = 0.09  # $0.09 / GB internet egress from AWS
        aws_exit_toll = estimated_data_gb * aws_egress_rate
        daily_savings = (total_savings / 30.0) if total_savings > 0 else 1.0
        amortization_days = round(aws_exit_toll / daily_savings, 1)

        gravity = NetworkGravityReport(
            data_volume_gb=estimated_data_gb,
            aws_egress_rate_per_gb=aws_egress_rate,
            aws_exit_toll=round(aws_exit_toll, 2),
            gcp_ingress_cost=0.00,
            amortization_days=amortization_days,
            gcp_tooling="Google Cloud Storage Transfer Service (100% Free Ingress & Automated Checksum Verification)"
        )

        return FinOpsReport(
            items=items,
            total_aws_cost=round(total_aws, 2),
            total_gcp_cost=round(total_gcp, 2),
            total_savings=round(total_savings, 2),
            savings_percentage=round(savings_pct, 1),
            network_gravity=gravity
        )
