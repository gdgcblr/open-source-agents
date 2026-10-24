import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from analyzer import analyze_drift
from schemas import DriftSeverity
from guardrails import validate_file_path, GuardrailValidationError

load_dotenv()
console = Console()


def main():
    parser = argparse.ArgumentParser(
        description="API Contract & Gateway Security Drift Agent"
    )
    parser.add_argument(
        "--code",
        type=str,
        default="samples/UserController.java",
        help="Path to backend controller file",
    )
    parser.add_argument(
        "--spec",
        type=str,
        default="samples/openapi.json",
        help="Path to OpenAPI/Swagger spec file",
    )
    parser.add_argument(
        "--output-md",
        type=str,
        default="drift_report.md",
        help="Markdown file path to save report",
    )

    args = parser.parse_args()

    try:
        code_path = validate_file_path(Path(args.code))
        spec_path = validate_file_path(Path(args.spec))
    except GuardrailValidationError as gv_err:
        console.print(Panel(f"[bold red]Input Guardrail Violation:[/bold red]\n{gv_err}", title="Security Guardrail", border_style="red"))
        sys.exit(1)

    console.print(
        Panel.fit(
            f"[bold cyan]API Contract & Security Drift Agent[/bold cyan]\n"
            f"Code: [dim]{code_path}[/dim] | Spec: [dim]{spec_path}[/dim]\n"
            f"Modules: [green]Schema Parity + Gateway Security & Policy Drift Checker[/green]",
            border_style="cyan",
        )
    )

    code_content = code_path.read_text(encoding="utf-8")
    spec_content = spec_path.read_text(encoding="utf-8")

    with console.status("[bold green]Auditing contract parity and security posture with Gemini 3.8 Flash..."):
        try:
            report = analyze_drift(code_content, spec_content)
        except GuardrailValidationError as gv_err:
            console.print(Panel(f"[bold red]Execution Halted by Guardrail:[/bold red]\n{gv_err}", title="Security Triggered", border_style="red"))
            sys.exit(1)
        except Exception as e:
            console.print(f"[bold red]Runtime Error:[/bold red] {e}")
            sys.exit(1)

    # 1. Summary Panel
    status_color = "red" if (report.has_breaking_changes or not report.security_audit_passed) else "green"
    status_label = "POLICY / CONTRACT BREACH DETECTED" if (report.has_breaking_changes or not report.security_audit_passed) else "CONTRACT & POLICY COMPLIANT"
    sec_badge = "[bold green]PASSED[/bold green]" if report.security_audit_passed else "[bold red]FAILED (UNGUARDED ROUTES FOUND)[/bold red]"

    console.print(
        Panel(
            f"[bold {status_color}]{status_label}[/bold {status_color}]\n\n"
            f"Security Policy Audit: {sec_badge}\n"
            f"{report.summary}",
            title="Analysis Assessment",
            border_style=status_color,
        )
    )

    # 2. Security Posture Table
    if report.security_evaluations:
        sec_table = Table(title="Gateway Security & Policy Evaluation", show_header=True, header_style="bold yellow")
        sec_table.add_column("Endpoint", width=22)
        sec_table.add_column("Spec Required Schemes", width=22)
        sec_table.add_column("Spec Roles/Scopes", width=20)
        sec_table.add_column("Code Annotations", width=25)
        sec_table.add_column("Compliant?", width=12)

        for sec in report.security_evaluations:
            comp_badge = "[green]YES[/green]" if sec.is_compliant else "[red]NO (VULNERABLE)[/red]"
            sec_table.add_row(
                sec.endpoint,
                ", ".join(sec.expected_auth_schemes) if sec.expected_auth_schemes else "[dim]None (Public)[/dim]",
                ", ".join(sec.expected_scopes_or_roles) if sec.expected_scopes_or_roles else "[dim]None[/dim]",
                ", ".join(sec.code_auth_annotations) if sec.code_auth_annotations else "[red]Missing Auth Guard[/red]",
                comp_badge,
            )
        console.print(sec_table)

    # 3. Comprehensive Drift Table
    table = Table(title="Detected Parity & Security Drift Items", show_header=True, header_style="bold magenta")
    table.add_column("Severity", width=12)
    table.add_column("Endpoint", width=22)
    table.add_column("Type", width=24)
    table.add_column("Spec vs Code", width=34)
    table.add_column("Remediation", width=30)

    for item in report.drift_items:
        if item.severity == DriftSeverity.CRITICAL:
            sev_color = "bold white on red"
        elif item.severity == DriftSeverity.BREAKING:
            sev_color = "red"
        elif item.severity == DriftSeverity.WARNING:
            sev_color = "yellow"
        else:
            sev_color = "blue"

        table.add_row(
            f"[{sev_color}]{item.severity.value}[/{sev_color}]",
            item.endpoint,
            item.drift_type.value,
            f"[dim]Spec:[/dim] {item.spec_state}\n[dim]Code:[/dim] {item.code_state}",
            item.remediation,
        )

    console.print(table)

    # 4. Generate Markdown
    md_content = f"# API Contract & Security Policy Drift Report\n\n"
    md_content += f"- **Contract Parity Status:** {'BREAKING CHANGES FOUND' if report.has_breaking_changes else 'COMPLIANT'}\n"
    md_content += f"- **Security Policy Audit:** {'FAILED' if not report.security_audit_passed else 'PASSED'}\n\n"
    md_content += f"## Summary\n{report.summary}\n\n"

    if report.security_evaluations:
        md_content += f"## Security Policy Evaluations\n| Endpoint | Spec Auth | Spec Roles/Scopes | Code Guards | Compliant |\n|---|---|---|---|---|\n"
        for s in report.security_evaluations:
            md_content += f"| `{s.endpoint}` | {', '.join(s.expected_auth_schemes) or 'None'} | {', '.join(s.expected_scopes_or_roles) or 'None'} | {', '.join(s.code_auth_annotations) or 'None'} | {'YES' if s.is_compliant else '**NO**'} |\n"
        md_content += "\n"

    md_content += f"## Drift Occurrences\n"
    for item in report.drift_items:
        md_content += f"- **[{item.severity.value}] `{item.endpoint}` - `{item.drift_type.value}`**\n"
        md_content += f"  - Spec: {item.spec_state}\n"
        md_content += f"  - Code: {item.code_state}\n"
        md_content += f"  - Remediation: {item.remediation}\n\n"

    if report.suggested_security_patch:
        md_content += f"## Suggested Security Remediation Patch\n```java\n{report.suggested_security_patch}\n```\n"

    if report.suggested_spec_patch:
        md_content += f"## Suggested OpenAPI Spec Patch\n```json\n{report.suggested_spec_patch}\n```\n"

    Path(args.output_md).write_text(md_content, encoding="utf-8")
    console.print(f"\n[bold green]✓[/bold green] Full Markdown report generated: [underline]{args.output_md}[/underline]")


if __name__ == "__main__":
    main()