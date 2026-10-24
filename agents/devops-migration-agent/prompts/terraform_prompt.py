"""Prompts for Terraform and Infrastructure as Code migration analysis."""

TERRAFORM_SYSTEM_INSTRUCTION = """\
You are an Infrastructure-as-Code (IaC) and Cloud Architecture specialist.
You evaluate Terraform configurations intended for automated CI/CD pipelines in Azure DevOps, \
focusing on state storage security, service connections, and approval gates.
"""

TERRAFORM_ANALYSIS_PROMPT = """\
Review the following Terraform static analysis findings:

Discovered Files: {file_count}
Providers: {providers}
Backend Type: {backend_type}
Resources Count: {resources_count}
Required Service Connections: {service_connections}
Findings:
{findings}

Recommend:
1. Exact Azure DevOps Service Connection configuration (ARM Workload Identity Federation).
2. Remote state backend best practices (Azure Storage Account blob locking).
3. Pipeline staging structure (Plan on PR -> Approval gate -> Apply on main).
"""
