"""Command Line Interface for SecurePR Agent."""
import os
import sys
import argparse
from typing import Optional

try:
    import typer
    from rich.console import Console
    from rich.prompt import Prompt
    HAS_RICH = True
    app = typer.Typer(help="SecurePR Agent: GitHub PR Security CLI & Conversational Reviewer.")
    console = Console()
except ImportError:
    HAS_RICH = False
    class DummyApp:
        def command(self, *args, **kwargs):
            def decorator(fn):
                return fn
            return decorator
    app = DummyApp()

    class DummyTyperModule:
        @staticmethod
        def Option(default=None, *args, **kwargs):
            return default
    typer = DummyTyperModule()

    class FallbackConsole:
        def print(self, *args, **kwargs):
            text = " ".join(str(a) for a in args)
            import re
            clean_text = re.sub(r'\[/?(?:bold|green|red|blue|yellow|cyan|magenta)[^\]]*\]', '', text)
            print(clean_text)

    console = FallbackConsole()

from securepr_agent.agent import SecurePRAgent
from securepr_agent.github_client import GitHubClient
from securepr_agent.models import ExposureContext, Severity
from securepr_agent.reporters.json_report import generate_json_report
from securepr_agent.reporters.markdown import render_markdown_report


@app.command()
def scan(
    path: str = typer.Option(".", "--path", "-p", help="Root repository directory"),
    base_ref: str = typer.Option("origin/main", "--base", "-b", help="Base git ref for diff isolation"),
    fail_on: str = typer.Option("HIGH", "--fail-on", help="Gate failure threshold (CRITICAL, HIGH, MEDIUM)"),
    exposure: str = typer.Option("PUBLIC", "--exposure", help="Asset exposure context (PUBLIC, AUTHENTICATED, INTERNAL)"),
    md_out: Optional[str] = typer.Option(None, "--md-out", help="Path to write Markdown summary"),
    json_out: Optional[str] = typer.Option(None, "--json-out", help="Path to write JSON report"),
):
    """Run automated CI/CD security gate scan over local files/diff."""
    console.print(f"[bold blue]SecurePR Agent[/bold blue] scanning: [green]{path}[/green]")

    files = []
    for root, _, filenames in os.walk(path):
        for name in filenames:
            if name.endswith((".py", ".env", ".json", ".ts", ".js", ".yml", ".yaml")):
                full = os.path.join(root, name)
                if "/." in full or "\\." in full:
                    continue
                try:
                    with open(full, "r", encoding="utf-8", errors="ignore") as f:
                        files.append({"path": os.path.relpath(full, path), "content": f.read()})
                except Exception:
                    pass

    agent = SecurePRAgent(
        files=files,
        exposure=ExposureContext(exposure.upper()),
        fail_on=Severity(fail_on.upper()),
    )

    report = agent.scan()

    if md_out:
        with open(md_out, "w", encoding="utf-8") as f:
            f.write(render_markdown_report(report))
        console.print(f"[green]Markdown report written to: {md_out}[/green]")

    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            f.write(generate_json_report(report))
        console.print(f"[green]JSON report written to: {json_out}[/green]")

    console.print("\n--- [bold]SecurePR Scan Verdict[/bold] ---")
    console.print(f"Total Findings: {report.total_findings}")
    console.print(f"Attack Path Hypotheses: {len(report.attack_path_hypotheses)}")
    console.print(f"Redacted Secrets: {report.redacted_item_count}")

    if not report.passed_gate:
        console.print(f"[bold red]Pull Request Gate FAILED[/bold red]: Findings violate threshold '{fail_on}'.")
        sys.exit(1)
    else:
        console.print("[bold green]Pull Request Gate PASSED[/bold green]: Ready to merge.")
        sys.exit(0)


@app.command(name="scan-pr")
def scan_pr(
    pr_url: str = typer.Option(..., "--pr-url", "-u", help="GitHub Pull Request URL"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="GitHub Token"),
    fail_on: str = typer.Option("HIGH", "--fail-on", help="Gate failure threshold"),
    exposure: str = typer.Option("PUBLIC", "--exposure", help="Asset exposure"),
    post_comment: bool = typer.Option(False, "--post-comment", help="Post review comment to GitHub PR"),
    md_out: Optional[str] = typer.Option(None, "--md-out", help="Write Markdown report"),
):
    """Scan a remote GitHub Pull Request by URL."""
    console.print(f"[bold blue]SecurePR Agent[/bold blue] fetching GitHub PR: [green]{pr_url}[/green]")

    client = GitHubClient(token=token)
    try:
        pr_meta = client.fetch_pull_request(pr_url)
    except Exception as e:
        console.print(f"[bold red]Failed to fetch PR:[/bold red] {e}")
        sys.exit(1)

    files = []
    for f in pr_meta.files:
        files.append({"path": f.filename, "content": f.patch or ""})

    agent = SecurePRAgent(
        files=files,
        exposure=ExposureContext(exposure.upper()),
        fail_on=Severity(fail_on.upper()),
    )

    report = agent.scan()
    md_report = render_markdown_report(report)

    if md_out:
        with open(md_out, "w", encoding="utf-8") as mf:
            mf.write(md_report)

    if post_comment:
        ok = client.post_comment(pr_url, md_report)
        if ok:
            console.print("[bold green]Posted review comment to GitHub PR successfully.[/bold green]")
        else:
            console.print("[yellow]Could not post review comment (check token permissions).[/yellow]")

    if not report.passed_gate:
        console.print(f"[bold red]PR Gate BLOCKED[/bold red]: Threshold '{fail_on}' violated.")
        sys.exit(1)
    else:
        console.print("[bold green]PR Gate PASSED[/bold green]: All checks clear.")
        sys.exit(0)


@app.command()
def chat(
    pr_url: Optional[str] = typer.Option(None, "--pr-url", "-u", help="GitHub Pull Request URL"),
    path: str = typer.Option(".", "--path", "-p", help="Local directory path"),
):
    """Start an interactive multi-turn conversational review session."""
    console.print("[bold blue]SecurePR AI Interactive Conversational Agent[/bold blue]")
    console.print("Type your questions or requests (e.g. 'Explain finding 1', 'Propose an RS256 fix', 'verify fix'). Type 'exit' to quit.\n")

    files = []
    if pr_url:
        console.print(f"Loading GitHub PR: {pr_url}...")
        try:
            client = GitHubClient()
            pr_meta = client.fetch_pull_request(pr_url)
            for f in pr_meta.files:
                files.append({"path": f.filename, "content": f.patch or ""})
        except Exception as e:
            console.print(f"[yellow]Could not fetch PR ({e}); falling back to local files.[/yellow]")

    if not files:
        for root, _, filenames in os.walk(path):
            for name in filenames:
                if name.endswith((".py", ".env", ".ts", ".js")):
                    full = os.path.join(root, name)
                    if "/." not in full:
                        try:
                            with open(full, "r", encoding="utf-8", errors="ignore") as f:
                                files.append({"path": os.path.relpath(full, path), "content": f.read()})
                        except Exception:
                            pass

    agent = SecurePRAgent(files=files)
    report = agent.scan()

    console.print(f"[bold green]Scan complete:[/bold green] Found {report.total_findings} items. Gate: {'PASSED' if report.passed_gate else 'BLOCKED'}\n")

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]You[/bold cyan]")
            if user_input.strip().lower() in ["exit", "quit", "q"]:
                break
            response = agent.chat_turn(user_input)
            console.print(f"\n[bold green]SecurePR Agent[/bold green]:\n{response}\n")
        except (KeyboardInterrupt, EOFError):
            break


@app.command()
def benchmark():
    """Run the empirical evaluation benchmark suite measuring Precision, Recall, FPR, and Secret Leakage."""
    from securepr_agent.benchmark import run_evaluation_benchmark

    console.print("[bold blue]Running SecurePR Empirical Benchmark Suite...[/bold blue]")
    results = run_evaluation_benchmark()

    summary = results["summary"]
    cm = results["confusion_matrix"]

    console.print("\n=== [bold]Evaluation Metrics Scorecard[/bold] ===")
    console.print(f"• Precision: [bold green]{summary['precision']}%[/bold green]")
    console.print(f"• Recall (Sensitivity): [bold green]{summary['recall']}%[/bold green]")
    console.print(f"• False-Positive Rate: [bold yellow]{summary['false_positive_rate']}%[/bold yellow]")
    console.print(f"• F1 Score: [bold green]{summary['f1_score']}[/bold green]")
    console.print(f"• Fix-Verification Accuracy: [bold green]{summary['fix_verification_accuracy']}%[/bold green]")
    console.print(f"• Evidence Correctness: [bold green]{summary['evidence_correctness']}%[/bold green]")
    console.print(f"• Secret Leakage Rate: [bold cyan]{summary['secret_leakage_rate']}%[/bold cyan] (synthetic cases only)")

    console.print(f"\nConfusion Matrix (N={cm['total_cases']}): TP={cm['true_positives']}, FP={cm['false_positives']}, TN={cm['true_negatives']}, FN={cm['false_negatives']}")


if __name__ == "__main__":
    # Ensure current package can be imported if executed directly
    pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)

    if HAS_RICH:
        app()
    else:
        parser = argparse.ArgumentParser(description="SecurePR Agent: PR Security CLI")
        subparsers = parser.add_subparsers(dest="command")

        # scan
        scan_p = subparsers.add_parser("scan", help="Scan local files")
        scan_p.add_argument("--path", "-p", default=".")
        scan_p.add_argument("--fail-on", default="HIGH")
        scan_p.add_argument("--exposure", default="PUBLIC")
        scan_p.add_argument("--md-out", default=None)
        scan_p.add_argument("--json-out", default=None)

        # scan-pr
        pr_p = subparsers.add_parser("scan-pr", help="Scan remote GitHub PR")
        pr_p.add_argument("--pr-url", "-u", required=True)
        pr_p.add_argument("--token", "-t", default=None)
        pr_p.add_argument("--fail-on", default="HIGH")
        pr_p.add_argument("--exposure", default="PUBLIC")
        pr_p.add_argument("--post-comment", action="store_true")
        pr_p.add_argument("--md-out", default=None)

        # chat
        chat_p = subparsers.add_parser("chat", help="Start conversational review")
        chat_p.add_argument("--pr-url", "-u", default=None)
        chat_p.add_argument("--path", "-p", default=".")

        # benchmark
        subparsers.add_parser("benchmark", help="Run empirical benchmark suite")

        args = parser.parse_args()
        if args.command == "benchmark":
            benchmark()
        elif args.command == "scan":
            scan(path=args.path, fail_on=args.fail_on, exposure=args.exposure, md_out=args.md_out, json_out=args.json_out)
        elif args.command == "scan-pr":
            scan_pr(pr_url=args.pr_url, token=args.token, fail_on=args.fail_on, exposure=args.exposure, post_comment=args.post_comment, md_out=args.md_out)
        elif args.command == "chat":
            chat(pr_url=args.pr_url, path=args.path)
        else:
            parser.print_help()
