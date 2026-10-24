import argparse
import sys
import os
from dotenv import load_dotenv
from agent import TracePilotAgent

def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="TracePilot: From Test Failure to Reproducible Bug")
    parser.add_argument("--file", "-f", type=str, help="Path to error log or test output file")
    parser.add_argument("--output", "-o", type=str, help="Path to save markdown bug report (optional)")
    args = parser.parse_args()

    # Read log content from file or stdin
    if args.file:
        if not os.path.exists(args.file):
            print(f"Error: Log file not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        with open(args.file, "r") as f:
            log_content = f.read()
    else:
        # Default to sample_error.log if it exists, else read from stdin
        sample_path = os.path.join(os.path.dirname(__file__), "sample_error.log")
        if os.path.exists(sample_path):
            print(f"No log file specified. Using default sample log: {sample_path}\n")
            with open(sample_path, "r") as f:
                log_content = f.read()
        else:
            print("Reading log content from stdin (Ctrl+D to end)...")
            log_content = sys.stdin.read()

    agent = TracePilotAgent()
    print("🚀 TracePilot AI Agent investigating failure and extracting evidence...")
    result = agent.investigate(log_content)
    markdown_report = agent.render_markdown_report(result)

    print("\n" + "="*80)
    print(markdown_report)
    print("="*80 + "\n")

    if args.output:
        with open(args.output, "w") as f:
            f.write(markdown_report)
        print(f"✅ Bug report successfully saved to {args.output}")

if __name__ == "__main__":
    main()
