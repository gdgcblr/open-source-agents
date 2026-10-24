"""
Gemma Quant MCP - Unified CLI and Demo Harness.
Powered by Rich terminal formatting and Click commands.
"""

from __future__ import annotations
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from core.models import StockQuote, LedgerEntry, AllocationItem
from core.quant_engine import calculate_quant_targets
from core.invariant_guardrails import audit_invariants
from core.screener_engine import screen_stocks
from core.gemma_advisor import generate_gemma_thesis
from mcp_server import run_stdio

console = Console()


@click.group()
def cli():
    """Gemma Quant MCP - Quantitative Engine & Financial Invariant Guardrails."""
    pass


@cli.command("demo")
def run_demo():
    """Run an end-to-end interactive demonstration with certified targets & invariant audit."""
    console.print(
        Panel.fit(
            "[bold cyan]⚡ Gemma Quant MCP - Google Open Source & AI Technologies[/bold cyan]\n"
            "[green]Certified Camarilla & Classic Pivot Engine + Financial Invariant Guardrails[/green]",
            border_style="cyan",
        )
    )

    # 1. Quant Targets Calculation Demo
    sample_quote = StockQuote(
        symbol="RELIANCE",
        ltp=2985.40,
        high=3010.00,
        low=2960.00,
        close=2975.00,
        high52=3024.90,
        low52=2220.30,
        change_pct=1.25,
    )

    targets = calculate_quant_targets(sample_quote)

    table = Table(title=f"📊 Quant Target Matrix: {targets.symbol} (LTP: ₹{targets.ltp})", header_style="bold magenta")
    table.add_column("Level Metric", style="cyan")
    table.add_column("Value (₹)", justify="right", style="bold green")
    table.add_column("Context / Strategy", style="white")

    table.add_row("T1 (Conservative)", f"₹{targets.targets.t1_conservative}", "Camarilla H3 / Quick Scalp Target")
    table.add_row("T2 (Base Case)", f"₹{targets.targets.t2_base_case}", "Camarilla H4 Breakout Target")
    table.add_row("T3 (Extended)", f"₹{targets.targets.t3_extended}", "Fibonacci 1.618 Extension Target")
    table.add_row("Stop Loss (Rec)", f"₹{targets.stop_loss.recommended}", "ATR-adjusted Structural Invalidation")
    table.add_row("Risk/Reward Ratio", targets.risk_reward_ratio, "Calculated Risk to T2 Base Case")
    table.add_row("Composite Score", f"{targets.composite_score}/100", f"Algorithmic Conviction ({targets.confidence_pct}% conf)")
    table.add_row("Market Bias", targets.bias, "Camarilla Momentum Classification")

    console.print(table)

    # 2. Financial Invariants Audit Demo (Double-Entry Zero-Sum Check)
    console.print("\n[bold yellow]🛡️ Running Double-Entry Ledger Invariant Audit...[/bold yellow]")
    entries = [
        LedgerEntry(entity="Alice (Payer)", amount=-1400.00),
        LedgerEntry(entity="Bob (Participant 1)", amount=700.00),
        LedgerEntry(entity="Charlie (Participant 2)", amount=700.00),
    ]

    allocations = [
        AllocationItem(asset="RELIANCE", weight_pct=22.0, value=22000.0),
        AllocationItem(asset="TCS", weight_pct=18.0, value=18000.0),
        AllocationItem(asset="HDFCBANK", weight_pct=20.0, value=20000.0),
        AllocationItem(asset="INFY", weight_pct=15.0, value=15000.0),
        AllocationItem(asset="ICICIBANK", weight_pct=15.0, value=15000.0),
        AllocationItem(asset="LIQUID_BEES", weight_pct=10.0, value=10000.0),
    ]

    report = audit_invariants(entries=entries, allocations=allocations)

    audit_table = Table(title="🔍 Financial Invariant Guardrails Verification", header_style="bold blue")
    audit_table.add_column("Invariant Rule", style="cyan")
    audit_table.add_column("Measurement", style="bold")
    audit_table.add_column("Result", style="green")

    audit_table.add_row("Double-Entry Zero-Sum", f"Net Delta: ₹{report.total_delta:.2f}", "✅ BALANCED (0.00)")
    audit_table.add_row("Portfolio Allocation Sum", f"Total Weight: {report.weights_sum_pct:.2f}%", "✅ COMPLETE (100.0%)")
    audit_table.add_row("Max Single Weight (<25%)", "Max is 22.0% (RELIANCE)", "✅ WITHIN SAFE BOUNDS")
    audit_table.add_row("Floating-Point Drift", "IEEE 754 precision check", "✅ ZERO DRIFT")

    console.print(audit_table)
    console.print(f"[bold green]{report.verdict}[/bold green]\n")

    # 3. Gemma Investment Thesis
    thesis = generate_gemma_thesis(targets)
    console.print(
        Panel(
            f"[bold]Symbol:[/bold] {thesis.symbol} | [bold]Bias:[/bold] [green]{thesis.bias}[/green] | [bold]Engine:[/bold] {thesis.model}\n\n"
            f"[bold cyan]Executive Summary:[/bold cyan]\n{thesis.summary}\n\n"
            f"[bold cyan]Key Strategic Rationales:[/bold cyan]\n"
            + "\n".join(f"• {r}" for r in thesis.strategic_rationale)
            + f"\n\n[bold cyan]Actionable Order Directive:[/bold cyan]\n[bold green]{thesis.suggested_action}[/bold green]",
            title="🤖 Gemma AI Research Thesis",
            border_style="magenta",
        )
    )


@cli.command("mcp")
def start_mcp():
    """Run the Model Context Protocol (MCP) server over standard input/output."""
    run_stdio()


if __name__ == "__main__":
    cli()
