import os
from pathlib import Path
from migrator.parser import TerraformParser, AWSResource
from migrator.mapper import get_service_mapping, get_gcp_region
from migrator.generator import MigrationGenerator
from migrator.agent import MigrationAgent
from migrator.topology_agent import TopologyAgent
from migrator.finops_agent import FinOpsPredictorAgent


def test_mapper_region_and_services():
    assert get_gcp_region("us-east-1") == "us-east1"
    assert get_gcp_region("ap-south-1") == "asia-south1"

    mapping = get_service_mapping("aws_s3_bucket")
    assert mapping["gcp_service"] == "Cloud Storage"
    assert mapping["gcp_resource"] == "google_storage_bucket"


def test_topology_agent_graph():
    res1 = AWSResource(
        resource_type="aws_s3_bucket",
        resource_name="data_bucket",
        raw_block='resource "aws_s3_bucket" "data_bucket" { bucket = "prod-data" }'
    )
    res2 = AWSResource(
        resource_type="aws_lambda_function",
        resource_name="processor",
        raw_block='resource "aws_lambda_function" "processor" { BUCKET = aws_s3_bucket.data_bucket.id }'
    )

    topo_agent = TopologyAgent()
    graph = topo_agent.build_graph([res1, res2])

    assert len(graph.edges) == 1
    assert graph.edges[0].source == "processor"
    assert graph.edges[0].target == "data_bucket"
    assert "flowchart TD" in graph.aws_mermaid
    assert "flowchart TD" in graph.gcp_mermaid


def test_finops_predictor_agent():
    res1 = AWSResource(
        resource_type="aws_lambda_function",
        resource_name="func",
        raw_block=""
    )
    res2 = AWSResource(
        resource_type="aws_s3_bucket",
        resource_name="bucket",
        raw_block=""
    )

    finops_agent = FinOpsPredictorAgent()
    report = finops_agent.predict_tco([res1, res2])

    assert report.total_aws_cost > 0
    assert report.total_gcp_cost > 0
    assert report.total_savings > 0
    assert report.savings_percentage > 0


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

    topo = TopologyAgent().build_graph([res1, res2])
    finops = FinOpsPredictorAgent().predict_tco([res1, res2])

    report = generator.generate_report([res1, res2], topology=topo, finops=finops)
    assert "AWS to Google Cloud Platform Migration Report" in report
    assert "Cloud Storage" in report
    assert "Cloud Pub/Sub" in report
    assert "FinOps Predictor" in report

    html = generator.generate_dashboard_html([res1, res2], topology=topo, finops=finops)
    assert "<!DOCTYPE html>" in html
    assert "AWS to GCP Migration" in html


def test_agent_three_agent_pipeline():
    agent = MigrationAgent(mock_mode=True)
    res = AWSResource(
        resource_type="aws_lambda_function",
        resource_name="worker",
        raw_block='resource "aws_lambda_function" "worker" {}',
        attributes={"function_name": "worker"}
    )

    topo, finops, insights = agent.run_pipeline(
        resources=[res],
        raw_code='resource "aws_lambda_function" "worker" {}',
        target_project="demo-project",
        target_region="us-central1"
    )

    assert topo is not None
    assert finops.total_savings > 0
    assert "Agent 2 (GCP Refactoring Engine)" in insights
    assert "Cloud Functions 2nd Gen" in insights


def test_google_adk_agent():
    from migrator.adk_adapter import GoogleADKMigrationAgent
    adk_agent = GoogleADKMigrationAgent(
        project_id="test-adk-proj",
        region="us-central1"
    )
    tools = adk_agent.get_tool_declarations()
    assert len(tools) == 3
    tool_names = [t.name for t in tools]
    assert "parse_infrastructure_topology" in tool_names
    assert "predict_finops_tco" in tool_names
    assert "generate_gcp_terraform" in tool_names

    res = adk_agent.execute_adk_pipeline("agents/aws-to-gcp-migrator/examples/aws_serverless.tf")
    assert "resources" in res
    assert "topology" in res
    assert "finops" in res
    assert "terraform" in res
