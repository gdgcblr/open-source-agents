"""
TrapDoor — entry point.

Usage:
  python main.py           # rich terminal output
  python main.py --json    # JSON report (for CI / scripting)
"""

import sys
from rich.console import Console

from trapdoor.agent.runner import run_session
from trapdoor.eval.evaluator import evaluate
from trapdoor.report.renderer import render_rich, render_json

console = Console()


def main() -> None:
    output_json = "--json" in sys.argv

    if not output_json:
        console.print("\n[bold cyan]TrapDoor[/bold cyan] — AI Agent Adversarial Testing\n")
        console.print("Running Gemini agent against trap MCP server...\n")

    session = run_session()
    report = evaluate(session)

    if output_json:
        print(render_json(report))
    else:
        render_rich(report)

    sys.exit(0 if report.verdict == "SAFE" else 1)


if __name__ == "__main__":
    main()
