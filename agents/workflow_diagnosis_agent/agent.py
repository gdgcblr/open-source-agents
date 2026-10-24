
import json
from pathlib import Path

from google.adk.agents import LlmAgent


def get_workflow_data() -> str:
    """Read workflow execution data from workflows.json."""

    data_file = Path(__file__).with_name("workflows.json")

    with data_file.open("r", encoding="utf-8") as file:
        workflows = json.load(file)

    return json.dumps(workflows, indent=2)


root_agent = LlmAgent(
    name="workflow_failure_diagnosis_agent",
    model="gemini-3.8-flash",
    description="Diagnoses data engineering workflow failures.",
    instruction="""
You are a data engineering workflow failure diagnosis agent.

1. Use the get_workflow_data tool to retrieve workflow execution data.
2. Identify successful and failed workflows.
3. Analyze the error message for each failed workflow.
4. Explain the probable root cause using available evidence.
5. Recommend practical debugging steps and potential fixes.
6. Clearly distinguish evidence from assumptions.
7. If evidence is insufficient, explain what additional logs are needed.
8. Never claim to have executed a fix or verified recovery.

Structure your response with:
- Overall summary
- Workflow-by-workflow status
- Probable cause
- Evidence
- Recommended next steps
""",
    tools=[get_workflow_data],
)
