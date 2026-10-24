"""CLI Entry point for Research Assistant Agent."""

import argparse
import os
import sys
from typing import Any, Dict

# Ensure UTF-8 output encoding on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Automatically load environment variables if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from agent.core import ResearchAgent


def format_step_console(record: Dict[str, Any]):
    """Pretty prints an agent step or observation to standard output."""
    if "step" in record:
        step_num = record["step"]
        thought = record.get("thought", "")
        action = record.get("action", "")
        action_input = record.get("action_input", {})
        
        print(f"\n[Step {step_num}]")
        print(f"  * Thought: {thought}")
        print(f"  * Action: {action}({action_input})")
    elif record.get("role") == "observation":
        obs = record.get("content")
        if isinstance(obs, list):
            print(f"  * Observation: Retrieved {len(obs)} search results.")
            for i, item in enumerate(obs[:2], 1):
                title = item.get("title", "")
                link = item.get("href", "")
                print(f"      [{i}] {title} ({link})")
        elif isinstance(obs, dict):
            status = obs.get("status", "")
            title = obs.get("title", "")
            chars = len(obs.get("content", ""))
            print(f"  * Observation [{status}]: {title} ({chars} chars)")


def run_research(topic: str, args: argparse.Namespace):
    """Executes research on a single topic."""
    print("=" * 70)
    print(f"[Research] Starting Research Assistant on Topic: '{topic}'")
    if args.mock:
        print("[Mode] OFFLINE MOCK MODE (Zero API key required)")
    else:
        print(f"[Mode] LIVE (Model: {args.model})")
    print("=" * 70)

    agent = ResearchAgent(
        model_name=args.model,
        max_steps=args.max_steps,
        mock_mode=args.mock,
        output_dir=args.output_dir,
        step_callback=format_step_console,
    )

    result = agent.run(topic)

    print("\n" + "=" * 70)
    print("[Success] Research Run Completed!")
    print(f"[Output] Markdown Dossier: {result['report_path']}")
    if "html_path" in result:
        print(f"[Output] HTML Dashboard:   {result['html_path']}")
    metrics = result.get("metrics", {})
    print(f"[Metrics] Run ID: {metrics.get('run_id', 'N/A')} | Duration: {metrics.get('duration_seconds', 0.0)}s")
    print(f"[Metrics] Steps: {result['steps_taken']} | Searches: {metrics.get('searches_performed', 0)} | Scraped: {metrics.get('pages_scraped', 0)} | Analyzed: {metrics.get('total_chars_analyzed', 0)} chars")
    print("=" * 70)
    print("\n--- REPORT PREVIEW ---\n")
    preview = result["final_report"][:800]
    print(preview)
    if len(result["final_report"]) > 800:
        print("\n[... Remaining content saved in report file ...]")
    print("\n" + "=" * 70)


def interactive_mode(args: argparse.Namespace):
    """Interactive REPL for multiple research sessions."""
    print("\n" + "=" * 70)
    print("[Console] Research Assistant Interactive Console")
    print("Type your research topic and press Enter. (Type 'exit' or 'quit' to end)")
    print("=" * 70)

    while True:
        try:
            topic = input("\nEnter research topic: ").strip()
            if not topic:
                continue
            if topic.lower() in ("exit", "quit", "q"):
                print("Goodbye!")
                break
            run_research(topic, args)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting Research Assistant. Goodbye!")
            break


def main():
    parser = argparse.ArgumentParser(
        description="Research Assistant Agent: Autonomous desk research with Google Gemini & DuckDuckGo."
    )
    parser.add_argument(
        "--topic", "-t",
        type=str,
        default=None,
        help="Research topic or question to investigate."
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive REPL mode."
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force offline mock mode for testing without requiring a live Gemini API key."
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("MODEL_NAME", "gemini-2.5-flash"),
        help="Gemini model identifier (default: gemini-2.5-flash)."
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=int(os.getenv("MAX_RESEARCH_STEPS", 5)),
        help="Maximum agent reasoning turns (default: 5)."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.getenv("OUTPUT_DIR", "reports"),
        help="Directory to save generated research reports (default: reports)."
    )

    args = parser.parse_args()

    # Default to mock if no GEMINI_API_KEY is present
    if not os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") == "your_gemini_api_key_here":
        if not args.mock:
            print("[Notice] No GEMINI_API_KEY detected in environment; enabling offline --mock mode automatically.")
            args.mock = True

    if args.interactive or not args.topic:
        interactive_mode(args)
    else:
        run_research(args.topic, args)


if __name__ == "__main__":
    main()
