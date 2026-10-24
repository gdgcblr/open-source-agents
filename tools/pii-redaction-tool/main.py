"""Main entry point for PII Compliance Redaction Agent."""
import sys
import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress

from config import settings
from pii_detector import PIIDetector
from redaction_engine import ComplianceRedactor
from guardrails import SecurityGuardrails
from evaluator import PIIEvaluator, TestDataManager


console = Console()


class PIIRedactionAgent:
    """Main agent orchestrating PII detection and redaction."""

    def __init__(self):
        """Initialize the agent."""
        self.detector = PIIDetector()
        self.redactor = ComplianceRedactor()
        self.guardrails = SecurityGuardrails()

    def process_text(
        self,
        text: str,
        strategy: Optional[str] = None,
        compliance_mode: Optional[str] = None
    ) -> dict:
        """
        Process text to detect and redact PII.

        Args:
            text: Input text to process
            strategy: Redaction strategy override
            compliance_mode: Compliance mode override

        Returns:
            Dict with results
        """
        try:
            # Validate input through guardrails
            self.guardrails.validate_request(text)

            # Detect PII
            entities = self.detector.detect_pii(text)

            # Filter by confidence
            filtered_entities = self.guardrails.filter_entities(entities)

            # Apply redaction
            if compliance_mode:
                self.redactor.compliance_mode = compliance_mode

            result = self.redactor.redact_with_compliance(text, filtered_entities, strategy=strategy)

            # Log detection
            self.guardrails.log_detection(text, filtered_entities)

            # Add entity details to result
            result["entities"] = [
                {
                    "text": e.text,
                    "category": e.category,
                    "confidence": e.confidence,
                    "method": e.detection_method
                }
                for e in filtered_entities
            ]

            return result

        except Exception as e:
            self.guardrails.log_detection(text, [], status="error", error=str(e))
            raise


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """PII Compliance Redaction Agent - Secure PII detection and redaction."""
    pass


@cli.command()
@click.argument('text', required=False)
@click.option('--file', '-f', type=click.Path(exists=True), help='Input file path')
@click.option('--output', '-o', type=click.Path(), help='Output file path')
@click.option('--strategy', '-s', type=click.Choice(['full', 'partial', 'hash', 'mask']), help='Redaction strategy')
@click.option('--compliance', '-c', type=click.Choice(['GDPR', 'CCPA', 'HIPAA', 'STRICT']), help='Compliance mode')
@click.option('--json-output', is_flag=True, help='Output as JSON')
def redact(text, file, output, strategy, compliance, json_output):
    """Redact PII from text or file."""
    agent = PIIRedactionAgent()

    # Get input text
    if file:
        with open(file, 'r', encoding='utf-8') as f:
            input_text = f.read()
    elif text:
        input_text = text
    else:
        console.print("[red]Error: Either --file or text argument is required[/red]")
        sys.exit(1)

    # Process
    with console.status("[bold green]Processing text..."):
        result = agent.process_text(input_text, strategy, compliance)

    # Output
    if json_output:
        console.print_json(json.dumps(result, indent=2))
    else:
        _print_rich_output(result, input_text)

    # Save to file if requested
    if output:
        with open(output, 'w', encoding='utf-8') as f:
            f.write(result["redacted_text"])
        console.print(f"[green]Output saved to {output}[/green]")


@cli.command()
@click.argument('text', required=False)
@click.option('--file', '-f', type=click.Path(exists=True), help='Input file path')
@click.option('--json-output', is_flag=True, help='Output as JSON')
def detect(text, file, json_output):
    """Detect PII in text without redaction."""
    agent = PIIRedactionAgent()

    # Get input text
    if file:
        with open(file, 'r', encoding='utf-8') as f:
            input_text = f.read()
    elif text:
        input_text = text
    else:
        console.print("[red]Error: Either --file or text argument is required[/red]")
        sys.exit(1)

    # Validate and detect
    try:
        agent.guardrails.validate_request(input_text)
        entities = agent.detector.detect_pii(input_text)
        filtered = agent.guardrails.filter_entities(entities)

        if json_output:
            output = {
                "entities": [
                    {
                        "text": e.text,
                        "category": e.category,
                        "confidence": e.confidence,
                        "start": e.start,
                        "end": e.end,
                        "method": e.detection_method
                    }
                    for e in filtered
                ],
                "total_count": len(filtered)
            }
            console.print_json(json.dumps(output, indent=2))
        else:
            _print_detection_results(filtered, input_text)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option('--data-path', default='test_data/', help='Path to test data')
@click.option('--output', '-o', type=click.Path(), help='Output report file')
def evaluate(data_path, output):
    """Run evaluation suite."""
    console.print("[bold blue]Running PII Redaction Agent Evaluation[/bold blue]")

    # Initialize
    agent = PIIRedactionAgent()
    test_manager = TestDataManager(data_path)
    evaluator = PIIEvaluator(agent.detector, agent.redactor)

    # Load test cases
    console.print("Loading test cases...")
    test_cases = test_manager.load_test_cases()

    if not test_cases:
        console.print("[yellow]No test cases found. Creating default test cases...[/yellow]")
        test_cases = test_manager._create_default_test_cases()
        test_manager.save_test_cases(test_cases)

    console.print(f"Loaded {len(test_cases)} test cases")

    # Run evaluation
    with Progress() as progress:
        task = progress.add_task("[green]Evaluating detection...", total=100)

        detection_result = evaluator.evaluate_detection(test_cases)
        progress.update(task, advance=50)

        redaction_result = evaluator.evaluate_redaction(test_cases)
        progress.update(task, advance=50)

    # Generate report
    report = evaluator.generate_report(detection_result, redaction_result)

    console.print("\n")
    console.print(Panel(report, title="Evaluation Report", border_style="blue"))

    # Save report if requested
    if output:
        with open(output, 'w', encoding='utf-8') as f:
            f.write(report)
        console.print(f"[green]Report saved to {output}[/green]")


@cli.command()
def audit():
    """View recent audit logs."""
    agent = PIIRedactionAgent()
    logs = agent.guardrails.get_audit_trail(limit=50)

    if not logs:
        console.print("[yellow]No audit logs found[/yellow]")
        return

    table = Table(title="Recent Audit Logs")
    table.add_column("Timestamp", style="cyan")
    table.add_column("Action", style="magenta")
    table.add_column("PII Count", style="green")
    table.add_column("Status", style="yellow")

    for log in logs:
        status_style = "green" if log.status == "success" else "red"
        table.add_row(
            log.timestamp,
            log.action,
            str(log.pii_count),
            f"[{status_style}]{log.status}[/{status_style}]"
        )

    console.print(table)


@cli.command()
def config():
    """Display current configuration."""
    table = Table(title="Current Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="magenta")

    config_dict = {
        "Model": settings.MODEL_NAME,
        "Confidence Threshold": str(settings.CONFIDENCE_THRESHOLD),
        "Redaction Strategy": settings.REDACTION_STRATEGY,
        "Compliance Mode": settings.COMPLIANCE_MODE,
        "Max Input Size": f"{settings.MAX_INPUT_SIZE} bytes",
        "Rate Limit": f"{settings.RATE_LIMIT_REQUESTS} / {settings.RATE_LIMIT_PERIOD}s",
        "Audit Logging": "Enabled" if settings.ENABLE_AUDIT_LOGGING else "Disabled",
        "Regex Detection": "Enabled" if settings.ENABLE_REGEX_DETECTION else "Disabled",
        "AI Detection": "Enabled" if settings.ENABLE_AI_DETECTION else "Disabled",
    }

    for key, value in config_dict.items():
        table.add_row(key, value)

    console.print(table)


@cli.command()
@click.option('--host', default='0.0.0.0', help='Host to bind to')
@click.option('--port', default=8000, type=int, help='Port to bind to')
def mcp_server(host, port):
    """Start MCP server for agent integration."""
    console.print(f"[bold green]Starting MCP server on {host}:{port}[/bold green]")
    console.print("[yellow]Agents can now connect to this MCP server to use PII redaction tools[/yellow]")
    import asyncio
    from mcp_server import main as mcp_main
    asyncio.run(mcp_main())


def _print_rich_output(result: dict, original_text: str):
    """Print rich formatted output."""
    console.print("\n")

    # Summary panel
    summary = f"""
[bold]PII Entities Found:[/bold] {result['entities_redacted']}
[bold]Compliance Mode:[/bold] {result['compliance_mode']}
[bold]Redaction Strategy:[/bold] {result['compliance_report']['redaction_strategy']}
[bold]Redaction Percentage:[/bold] {result['compliance_report']['redaction_percentage']}%
"""
    console.print(Panel(summary, title="Summary", border_style="green"))

    # Entities table
    if result['entities']:
        table = Table(title="Detected PII Entities")
        table.add_column("Category", style="cyan")
        table.add_column("Text", style="magenta")
        table.add_column("Confidence", style="yellow")
        table.add_column("Method", style="blue")

        for entity in result['entities']:
            table.add_row(
                entity['category'],
                entity['text'][:30] + "..." if len(entity['text']) > 30 else entity['text'],
                f"{entity['confidence']:.2f}",
                entity['method']
            )

        console.print(table)

    # Redacted text
    console.print("\n[bold]Redacted Text:[/bold]")
    console.print(Panel(result['redacted_text'], border_style="red"))


def _print_detection_results(entities, original_text):
    """Print detection results."""
    console.print("\n")

    if not entities:
        console.print("[green]No PII detected[/green]")
        return

    table = Table(title=f"Detected {len(entities)} PII Entities")
    table.add_column("Category", style="cyan")
    table.add_column("Text", style="magenta")
    table.add_column("Confidence", style="yellow")
    table.add_column("Position", style="blue")
    table.add_column("Method", style="green")

    for entity in entities:
        table.add_row(
            entity.category,
            entity.text[:30] + "..." if len(entity.text) > 30 else entity.text,
            f"{entity.confidence:.2f}",
            f"{entity.start}-{entity.end}",
            entity.detection_method
        )

    console.print(table)


if __name__ == "__main__":
    cli()
