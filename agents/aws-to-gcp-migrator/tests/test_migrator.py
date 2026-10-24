import os
from pathlib import Path
from migrator.parser import TerraformParser, AWSResource
from migrator.mapper import get_service_mapping, get_gcp_region
from migrator.generator import MigrationGenerator
from migrator.agent import MigrationAgent


def test_mapper_region_and_services():
    assert get_gcp_region("us-east-1") == "us-east1"
    assert get_gcp_region("ap-south-1") == "asia-south1"

    mapping = get_service_mapping("aws_s3_bucket")
    assert mapping["gcp_service"] == "Cloud Storage"
    assert mapping["gcp_resource"] == "google_storage_bucket"


def test_generator_terraform_and_report():
    res1 = AWSResource(
        resource_type="aws_s3_bucket",
        resource_name="data_bucket",
        raw_block='resource "aws_s3_bucket" "data_bucket" { bucket = "prod-data" }',
        attributes={"bucket": "prod-data"}
    )
    res2 = AWSResource(
        resource_type="aws_sqs_queue",
        resource_name="task_queue",
        raw_block='resource "aws_sqs_queue" "task_queue" { name = "jobs" }',
        attributes={"name": "jobs"}
    )

    generator = MigrationGenerator(project_id="test-project", region="us-central1")
    tf_content = generator.generate_terraform([res1, res2])

    assert "google_storage_bucket" in tf_content
    assert "google_pubsub_topic" in tf_content
    assert "google_project_service" in tf_content
    assert "test-project" in tf_content

    report = generator.generate_report([res1, res2])
    assert "AWS to Google Cloud Platform Migration Report" in report
    assert "Cloud Storage" in report
    assert "Cloud Pub/Sub" in report


def test_agent_mock_mode():
    agent = MigrationAgent(mock_mode=True)
    res = AWSResource(
        resource_type="aws_lambda_function",
        resource_name="worker",
        raw_block='resource "aws_lambda_function" "worker" {}',
        attributes={"function_name": "worker"}
    )

    insights = agent.analyze_migration(
        resources=[res],
        raw_code='resource "aws_lambda_function" "worker" {}',
        target_project="demo-project",
        target_region="us-central1"
    )

    assert "Automated Cloud Architecture Insights" in insights
    assert "Cloud Functions 2nd Gen" in insights
