
from datetime import datetime
import json
from pathlib import Path



def diagnose_workflow(workflow):
    """Analyze a workflow run and suggest a resolution."""

    status = workflow["status"].lower()
    error_message = workflow.get("error_message", "")
    error = error_message.lower()

    if status == "success":
        return {
            "workflow": workflow["name"],
            "status": "SUCCESS",
            "reason": "Workflow completed successfully.",
            "suggestion": "No action required.",
        }

    if "out of memory" in error or "memory" in error:
        reason = "The workflow may have exhausted available memory."
        suggestion = (
            "Check data volume, partition sizes, and memory settings."
        )

    elif "connection" in error:
        reason = "The workflow may have encountered a connection issue."
        suggestion = (
            "Check database availability, network connectivity, "
            "and credentials."
        )

    elif "timeout" in error:
        reason = "The workflow exceeded its allowed execution time."
        suggestion = (
            "Check task duration, upstream delays, and timeout settings."
        )

    else:
        reason = (
            "The failure cause could not be identified by current rules."
        )
        suggestion = (
            "Inspect the full error logs and upstream task status."
        )

    return {
        "workflow": workflow["name"],
        "status": "FAILED",
        "reason": reason,
        "suggestion": suggestion,
    }



def generate_daily_report(workflows):
    """Print a summary of workflow runs."""

    successful = 0
    failed = 0

    print(f"\nDAILY WORKFLOW REPORT - {datetime.now():%Y-%m-%d}")
    print("-" * 50)

    for workflow in workflows:
        result = diagnose_workflow(workflow)

        if result["status"] == "SUCCESS":
            successful += 1
        else:
            failed += 1

        print(f"\nWorkflow: {result['workflow']}")
        print(f"Status: {result['status']}")
        print(f"Reason: {result['reason']}")
        print(f"Suggested action: {result['suggestion']}")

    print("\n" + "-" * 50)
    print(f"Total workflows: {len(workflows)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    data_file = Path(__file__).with_name("workflows.json")

    with data_file.open("r", encoding="utf-8") as file:
        workflows = json.load(file)

    generate_daily_report(workflows)

