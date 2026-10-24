"""CLI Entry point for Multi-Agent Collaborative Editorial Pipeline."""

import argparse
import os
import sys
from typing import Any, Dict

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from team.orchestrator import EditorialOrchestrator
from team.tools.reporter import export_publication_artifacts


def handle_event(event: Dict[str, Any]):
    """Pretty prints collaborative agent actions to the terminal."""
    role = event.get("role", "").upper()
    msg = event.get("message", "")
    time_str = event.get("timestamp", "")
    event_type = event.get("event", "")

    if event_type == "agent_start":
        print(f"\n[{time_str}] 🚀 [{role}] Starting: {msg}")
    elif event_type == "agent_complete":
        print(f"[{time_str}] ✓  [{role}] Completed: {msg}")
    elif event_type == "circuit_breaker":
        print(f"\n[{time_str}] ⚠️  [CIRCUIT BREAKER] {msg}")


def run_pipeline(topic: str, args: argparse.Namespace):
    """Executes the full collaborative pipeline on a topic."""
    print("=" * 75)
    print(f"👥 Launching Multi-Agent Editorial Pipeline on: '{topic}'")
    if args.mock:
        print("[Mode] OFFLINE MOCK MODE (Zero API key required)")
    else:
        print(f"[Mode] LIVE GEMINI (Model: {args.model})")
    print(f"[Rules] Max Revisions: {args.max_revisions} | Pass Threshold: {args.pass_score}/100")
    print("=" * 75)

    orchestrator = EditorialOrchestrator(
        model_name=args.model,
        max_revisions=args.max_revisions,
        pass_score=args.pass_score,
        mock_mode=args.mock,
        event_callback=handle_event
    )

    state = orchestrator.run(topic)
    artifacts = export_publication_artifacts(state, output_dir=args.output_dir)

    metrics = state.metrics
    score = metrics.final_score if metrics else 85
    duration = metrics.duration_seconds if metrics else 0.0

    print("\n" + "=" * 75)
    print("🎉 Editorial Collaboration Completed!")
    print(f"[Quality Score] {score} / 100 ({'APPROVED' if state.is_approved else 'Best-Effort Published'})")
    print(f"[Revisions Made] {state.revision_turns} / {args.max_revisions}")
    print(f"[Markdown Article] {artifacts['markdown_path']}")
    print(f"[HTML Dashboard]   {artifacts['html_path']}")
    print(f"[Telemetry] Duration: {duration}s | Evidence: {len(state.evidence)} items | Messages: {len(state.messages)}")
    print("=" * 75)

    print("\n--- FINAL PUBLISHED ARTICLE PREVIEW ---\n")
    preview = state.current_draft[:900]
    print(preview)
    if len(state.current_draft) > 900:
        print("\n[... View complete article in Markdown and HTML files ...]")
    print("\n" + "=" * 75)


def interactive_mode(args: argparse.Namespace):
    """Interactive REPL for multiple editorial projects."""
    print("\n" + "=" * 75)
    print("🤖 Multi-Agent Editorial Pipeline Console")
    print("Enter a topic to generate a collaborative article. (Type 'exit' or 'quit' to end)")
    print("=" * 75)

    while True:
        try:
            topic = input("\nEnter editorial topic: ").strip()
            if not topic:
                continue
            if topic.lower() in ("exit", "quit", "q"):
                print("Exiting. Goodbye!")
                break
            run_pipeline(topic, args)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting. Goodbye!")
            break


def main():
    parser = argparse.ArgumentParser(
        description="Multi-Agent Editorial Team: Hierarchical Planner, Researcher, Writer, and Reviewer pipeline."
    )
    parser.add_argument(
        "--topic", "-t",
        type=str,
        default=None,
        help="Editorial topic or technical subject."
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive REPL mode."
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force offline mock mode without requiring an active Gemini API key."
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("MODEL_NAME", "gemini-2.5-flash"),
        help="Gemini model identifier (default: gemini-2.5-flash)."
    )
    parser.add_argument(
        "--max-revisions",
        type=int,
        default=int(os.getenv("MAX_REVISIONS", 2)),
        help="Maximum reviewer-guided revision cycles (default: 2)."
    )
    parser.add_argument(
        "--pass-score",
        type=int,
        default=int(os.getenv("CRITIQUE_PASS_SCORE", 85)),
        help="Quality score threshold required for approval (default: 85)."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.getenv("OUTPUT_DIR", "reports"),
        help="Directory to save publications (default: reports)."
    )

    args = parser.parse_args()

    if not os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") == "your_gemini_api_key_here":
        if not args.mock:
            print("[Notice] No GEMINI_API_KEY detected in environment; enabling offline --mock mode automatically.")
            args.mock = True

    if args.interactive or not args.topic:
        interactive_mode(args)
    else:
        run_pipeline(args.topic, args)


if __name__ == "__main__":
    main()
