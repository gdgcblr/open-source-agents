import os
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from agents.scholar_agent.schemas import ResearchPaperArtifacts

console = Console()

# to display rich tables and panels in the console output
def display_and_export(report: ResearchPaperArtifacts, output_dir: str):
    # 1. Summary
    console.print(Panel(
        f"[bold]{report.title}[/bold]\n[dim]{report.authors or 'No Author Info'}[/dim]\n\n{report.executive_summary}",
        title="[bold blue]Executive Summary[/bold blue]", border_style="blue"
    ))

    # 2. Insights
    console.print("\n[bold cyan]Key Technical Insights:[/bold cyan]")
    for i, ins in enumerate(report.key_insights, 1):
        console.print(f"  [bold green]{i}.[/bold green] {ins}")

    # 3. Tradeoffs
    console.print("\n[bold magenta]Tradeoffs & Limitations:[/bold magenta]")
    for lim in report.limitations_and_tradeoffs:
        console.print(f"  [bold red]•[/bold red] {lim}")

    # 4. Rich Table
    console.print(f"\n[bold yellow]Table: {report.comparative_table.title}[/bold yellow]")
    rich_table = Table(show_header=True, header_style="bold magenta")
    for h in report.comparative_table.headers:
        rich_table.add_column(h)
    for row in report.comparative_table.rows:
        rich_table.add_row(*row)
    console.print(rich_table)

    # 5. Diagram
    console.print("\n[bold green]Architecture Diagram (Mermaid):[/bold green]")
    console.print(Panel(report.diagram_mermaid, border_style="dim green"))

    # Write artifacts to disk
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "architecture.mmd"), "w", encoding="utf-8") as f:
        f.write(report.diagram_mermaid + "\n")
    
    with open(os.path.join(output_dir, "summary.md"), "w", encoding="utf-8") as f:
        f.write(f"# {report.title}\n\n{report.executive_summary}\n\n")
        f.write("## Key Insights\n" + "\n".join([f"- {k}" for k in report.key_insights]) + "\n\n")
        f.write("## Architecture Diagram\n```mermaid\n" + report.diagram_mermaid + "\n```\n")
    
    console.print(f"\n[dim]Artifacts exported to:[/dim] [bold]{output_dir}/[/bold]")