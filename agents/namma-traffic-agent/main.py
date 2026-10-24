"""
main.py - Interactive CLI for Namma Bengaluru Traffic Copilot
Supports natural language queries, rich terminal tables, and real-time transit insights.
"""

import sys
import argparse

# Ensure UTF-8 output encoding for Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn

from agent.core import NammaTrafficAgent

console = Console(highlight=False)


def print_banner():
    banner = """[bold cyan]
  _   _                                _____            __  __ _        
 | \\ | | __ _ _ __ ___  _ __ ___   __ |_   _| __ __ _ / _|/ _(_) ___   
 |  \\| |/ _` | '_ ` _ \\| '_ ` _ \\ / _` || || '__/ _` | |_| |_| |/ __|  
 | |\\  | (_| | | | | | | | | | | | (_| || || | | (_| |  _|  _| | (__   
 |_| \\_|\\__,_|_| |_| |_|_| |_| |_|\\__,_||_||_|  \\__,_|_| |_| |_|\\___|  
[/bold cyan]
[bold yellow]🚦 Real-time Bengaluru Traffic Copilot & Multimodal Commute Optimizer[/bold yellow]
[dim]Powered by Google GenAI (Gemini 2.5 Flash) + Local Transit Intelligence[/dim]
"""
    console.print(banner)


def display_result(result: dict):
    """Renders agent output with Rich UI elements."""
    console.print()
    mode = result.get("mode", "unknown")
    tools = result.get("tools_used", [])
    
    # Mode badge
    badge = f"[bold green]● Mode:[/bold green] {mode}"
    if result.get("fallback_reason"):
        badge += f" [dim]({result['fallback_reason']})[/dim]"
    console.print(badge)

    # Tool calls badge
    if tools:
        tool_names = ", ".join(f"[bold magenta]{t['tool']}[/bold magenta]" for t in tools)
        console.print(f"[bold blue]⚡ Tools Invocations:[/bold blue] {tool_names}")

    console.print()

    # Raw tool tables if available
    for data in result.get("raw_tool_data", []):
        if not isinstance(data, dict):
            continue
            
        # Route traffic table
        if data.get("origin") and data.get("destination") and "current_travel_time_mins" in data:
            table = Table(title=f"🚗 Commute Overview: {data['origin']} ➡️ {data['destination']}", title_style="bold yellow")
            table.add_column("Metric", style="cyan", no_wrap=True)
            table.add_column("Details", style="white")

            table.add_row("Distance", f"{data.get('distance_km')} km")
            table.add_row("Current Travel Time", f"[bold red]{data.get('current_travel_time_mins')} mins[/bold red]")
            table.add_row("Off-Peak Duration", f"{data.get('off_peak_time_mins')} mins")
            table.add_row("Traffic Congestion", data.get("congestion_category", "N/A"))
            table.add_row("Est. Auto Fare", f"₹{data.get('cost_estimates', {}).get('namma_auto_inr', 'N/A')}")
            table.add_row("Est. Cab Fare", f"₹{data.get('cost_estimates', {}).get('cab_uber_ola_inr', 'N/A')} (Surge: {data.get('cost_estimates', {}).get('surge_multiplier', '1.0x')})")
            console.print(table)
            console.print()

        # Metro table
        if "origin_boarding_station" in data and "breakdown" in data:
            m_table = Table(title=f"🚇 Namma Metro Multimodal Alternative", title_style="bold green")
            m_table.add_column("Stage", style="cyan")
            m_table.add_column("Station / Mode", style="white")
            m_table.add_column("Time", style="green")

            m_table.add_row("First Mile", data.get("origin_boarding_station"), f"~{data['breakdown']['first_mile_mins']} mins")
            m_table.add_row("Metro Train Ride", f"Interchange: {data.get('interchange_required')}", f"{data['breakdown']['train_ride_mins']} mins")
            m_table.add_row("Last Mile", data.get("destination_deboarding_station"), f"~{data['breakdown']['last_mile_mins']} mins")
            m_table.add_row("[bold]Total Time[/bold]", "[bold]Door-to-door[/bold]", f"[bold]{data['breakdown']['total_multimodal_time_mins']} mins[/bold]")
            m_table.add_row("[bold]Fare[/bold]", f"Metro ₹{data.get('metro_ticket_fare_inr')} + Auto", f"₹{data.get('total_transit_cost_inr')}")
            console.print(m_table)
            console.print()

        # Departure window table
        if "schedule_options" in data:
            d_table = Table(title=f"⏱️ Congestion Curve & Departure Optimization", title_style="bold magenta")
            d_table.add_column("Departure Time", style="cyan")
            d_table.add_column("Est. Commute Time", style="yellow")
            d_table.add_column("Congestion", style="white")

            for opt in data["schedule_options"]:
                is_best = (opt["departure_time"] == data.get("golden_departure_window"))
                style_prefix = "[bold green]⭐ " if is_best else ""
                style_suffix = " (Best)[/bold green]" if is_best else ""
                d_table.add_row(
                    f"{style_prefix}{opt['departure_time']}{style_suffix}",
                    f"{opt['estimated_minutes']} mins",
                    opt["congestion"]
                )
            console.print(d_table)
            console.print()

    # Formatted advice panel
    response_md = Markdown(result.get("response", ""))
    panel = Panel(
        response_md,
        title="[bold yellow]🤖 Namma Copilot Recommendation[/bold yellow]",
        border_style="cyan",
        padding=(1, 2)
    )
    console.print(panel)
    console.print()


def run_interactive(agent: NammaTrafficAgent, is_raining: bool = False):
    """Runs continuous REPL for the user."""
    print_banner()
    console.print("[dim]Type your query in natural language, or 'exit' / 'quit' to end.[/dim]")
    console.print("[dim]Examples:[/dim]")
    console.print("  [cyan]•[/cyan] 'How is traffic from Koramangala to Whitefield at 6 PM?'")
    console.print("  [cyan]•[/cyan] 'Is Silk Board junction jammed right now?'")
    console.print("  [cyan]•[/cyan] 'Should I take metro or cab from Indiranagar to Airport?'")
    console.print("  [cyan]•[/cyan] 'Any waterlogging alerts near Bellandur or Hebbal?'")
    console.print()

    while True:
        try:
            prompt = console.input("[bold cyan]NammaCommuter > [/bold cyan]").strip()
            if not prompt:
                continue
            if prompt.lower() in ["exit", "quit", "q"]:
                console.print("[yellow]Safe travels across Bengaluru! Namaskara! 🙏[/yellow]")
                break

            with Progress(
                SpinnerColumn(),
                TextColumn("[bold green]Analyzing Bengaluru traffic patterns...[/bold green]"),
                transient=True,
            ) as progress:
                progress.add_task("query", total=None)
                result = agent.query(prompt, is_raining=is_raining)

            display_result(result)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Exiting. Safe travels! 🙏[/yellow]")
            break


def main():
    parser = argparse.ArgumentParser(description="Namma Bengaluru Traffic Copilot AI Agent")
    parser.add_argument("query", nargs="*", help="Natural language transit query")
    parser.add_argument("--rain", action="store_true", help="Simulate heavy monsoon rain disruptions")
    parser.add_argument("--hour", type=int, default=None, help="Departure hour (0-23)")
    args = parser.parse_args()

    agent = NammaTrafficAgent()

    if args.query:
        full_query = " ".join(args.query)
        result = agent.query(full_query, is_raining=args.rain, target_hour=args.hour)
        print_banner()
        display_result(result)
    else:
        run_interactive(agent, is_raining=args.rain)


if __name__ == "__main__":
    main()
