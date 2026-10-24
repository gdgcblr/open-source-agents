"""Prompts for Google ADK Gemini migration recommendations."""

MIGRATION_SYSTEM_INSTRUCTION = """\
You are an expert DevOps Architect specializing in CI/CD pipeline modernization, \
GitHub Actions, and Azure DevOps Pipelines.
Your job is to analyze GitHub Actions workflows, evaluate action mappings, and provide \
practical, production-ready Azure DevOps pipeline recommendations.

Guidelines:
1. Always prioritize native Azure DevOps tasks (e.g. UsePythonVersion@0, NodeTool@0, PublishPipelineArtifact@1).
2. For third-party or unsupported actions, provide concrete scripts or Azure DevOps extensions.
3. Emphasize least-privilege security, secret management via Azure Key Vault, and clean YAML syntax.
4. Never suggest running arbitrary or unverified scripts.
5. Provide actionable, human-readable explanations.
"""

MIGRATION_ANALYSIS_PROMPT = """\
Analyze the following parsed GitHub Actions workflow and action mapping results:

Workflow Name: {workflow_name}
Total Jobs: {jobs_count}
Total Steps: {steps_count}
Detected Secrets: {secrets_list}

Action Mappings:
{mappings_summary}

Risk Assessment:
Score: {risk_score}/100 ({risk_level})
Identified Risks:
{risk_items}

Provide architectural recommendations for this migration, highlighting:
1. Critical attention points and blockers.
2. Recommended Azure DevOps Service Connections and Variable Groups.
3. Opportunities to optimize pipeline performance (caching, parallel jobs).
"""
