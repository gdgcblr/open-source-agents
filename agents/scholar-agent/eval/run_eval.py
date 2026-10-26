"""
run_eval.py - Automated Benchmark Evaluation Harness
Isolates each test run into a fresh ADK runner instance to prevent session collisions.
"""
import os
import sys
import json
import tempfile
import asyncio
from rich.console import Console
from rich.table import Table

# Ensure parent directory is in Python's search path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from rag_tool import load_and_index_document
from adk_agent import ADKScholarRunner
from guardrails import SecurityGuardrails
from metrics import evaluate_guardrail_neutralization, calculate_concept_recall, validate_schema_and_artifacts

console = Console()

async def run_benchmark():
    console.rule("[bold cyan]Scholar-Agent Benchmark Evaluation[/bold cyan]")
    
    dataset_path = os.path.join(os.path.dirname(__file__), "dataset.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        fixtures = json.load(f)

    guard = SecurityGuardrails()
    results = []

    for item in fixtures:
        test_id = item["id"]
        cohort = item["cohort"]
        console.print(f"\n[bold yellow]Testing [{cohort}]: {test_id}...[/bold yellow]")

        # 1. Ingestion & Indexing
        temp_file_path = None
        if "source" in item:
            source = item["source"]
            load_and_index_document(source)
            test_source = source
            raw_input_text = source
        else:
            # Handle synthetic adversarial text via temporary file
            synthetic_text = item["synthetic_text"]
            raw_input_text = synthetic_text
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as temp_f:
                temp_f.write(synthetic_text)
                temp_file_path = temp_f.name
            load_and_index_document(temp_file_path)
            test_source = temp_file_path

        # 2. Guardrail Check on Input
        guardrail_result = evaluate_guardrail_neutralization(
            raw_input=raw_input_text,
            sanitized_output_text=""
        )

        # 3. Create a FRESH Runner per test to isolate sessions and context memory
        runner = ADKScholarRunner(model_name="gemini-2.5-flash")

        # 4. Execute Analysis
        try:
            report = await runner.analyze(test_source)
            schema_check = validate_schema_and_artifacts(report)
            concept_score = calculate_concept_recall(
                report.executive_summary,
                report.key_insights,
                item.get("target_concepts", [])
            )
            
            # For adversarial payloads, verify if malicious commands leaked into the summary/diagram
            if item.get("has_injection", False):
                leak_check = evaluate_guardrail_neutralization(
                    raw_input=raw_input_text,
                    sanitized_output_text=f"{report.executive_summary} {report.diagram_mermaid}"
                )
                threat_neutralized = not leak_check["leak_detected"]
            else:
                threat_neutralized = True

            passed = schema_check["overall_valid"] and threat_neutralized

        except Exception as e:
            console.print(f"[bold red]Failed execution for {test_id}: {e}[/bold red]")
            schema_check = {"overall_valid": False, "valid_mermaid": False}
            concept_score = 0.0
            threat_neutralized = False
            passed = False

        finally:
            # Clean up temporary synthetic file if created
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)

        results.append({
            "id": test_id,
            "cohort": cohort,
            "passed": passed,
            "schema_valid": schema_check["overall_valid"],
            "concept_recall": concept_score,
            "threat_neutralized": threat_neutralized if item.get("has_injection", False) else "N/A"
        })

    # Render Aggregate Results Table
    console.rule("[bold green]Aggregate Evaluation Results[/bold green]")
    r_table = Table(show_header=True, header_style="bold magenta")
    r_table.add_column("Test ID")
    r_table.add_column("Cohort")
    r_table.add_column("Schema Valid")
    r_table.add_column("Concept Recall")
    r_table.add_column("Injection Defense")
    r_table.add_column("Status")

    for r in results:
        status_str = "[bold green]PASS[/bold green]" if r["passed"] else "[bold red]FAIL[/bold red]"
        r_table.add_row(
            r["id"],
            r["cohort"],
            str(r["schema_valid"]),
            f"{r['concept_recall']}%",
            str(r["threat_neutralized"]),
            status_str
        )

    console.print(r_table)

if __name__ == "__main__":
    asyncio.run(run_benchmark())