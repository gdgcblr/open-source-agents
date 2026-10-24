"""Command-line runner: a live spinner while the agents work, then only the final report.

    python review.py template          # review one folder
    python review.py                   # interactive: type a folder, get a report, repeat
    python review.py template --json   # raw JSON on stdout (spinner and errors go to stderr)

The model's own chatter (including any visible "thinking") is not shown; only the finalizer's
report is. Exit status is 0 when the verdict is "ready", otherwise 1. Standard library only.
"""

import argparse
import asyncio
import itertools
import logging
import os
import sys
import threading
import time
import warnings
from pathlib import Path

from .analysis.scoring import ReviewReport

PROJECT = Path(__file__).resolve().parents[1]
APP_NAME = "readme_reviewer"
FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
REVIEWERS = {
    "reproducibility_reviewer": "reproducibility",
    "documentation_reviewer": "documentation",
    "security_reviewer": "security",
    "scope_reviewer": "scope",
}
RESET, DIM, RED, GREEN, CYAN, BOLD = "\033[0m", "\033[2m", "\033[31m", "\033[32m", "\033[36m", "\033[1m"


def use_color(stream) -> bool:
    return stream.isatty() and "NO_COLOR" not in os.environ


# --- progress ---------------------------------------------------------------- #
class Progress:
    """Tracks which reviewers have finished and turns that into a one-line status."""

    def __init__(self):
        self.done = set()
        self.scoring = False

    def update(self, author: str, is_final: bool) -> None:
        if author in REVIEWERS and is_final:
            self.done.add(REVIEWERS[author])
        elif author == "review_aggregator":
            self.scoring = True

    def label(self) -> str:
        if self.scoring:
            return "Scoring the report"
        if len(self.done) == len(REVIEWERS):
            return "Merging the findings"
        return f"Reviewing: {len(self.done)}/{len(REVIEWERS)} reviewers done"


def format_status(frame: str, label: str, elapsed: float, color: bool = False) -> str:
    if color:
        return f"{CYAN}{frame}{RESET} {label} {DIM}({int(elapsed)}s){RESET}"
    return f"{frame} {label} ({int(elapsed)}s)"


class Spinner:
    """Animated one-line status on a terminal; plain progress lines when output is not a terminal."""

    def __init__(self, label, stream=None):
        self.label = label  # callable returning the current status text
        self.stream = stream or sys.stderr
        self.live = self.stream.isatty()
        self.color = use_color(self.stream)
        self._stop = threading.Event()
        self._thread = None
        self._start = 0.0
        self._last_plain = None

    def _write(self, text: str) -> None:
        self.stream.write(text)
        self.stream.flush()

    def _run(self) -> None:
        for frame in itertools.cycle(FRAMES):
            if self._stop.is_set():
                return
            self._write("\r\033[K" + format_status(frame, self.label(), time.time() - self._start, self.color))
            self._stop.wait(0.1)

    def tick(self) -> None:
        """Non-terminal mode: print the status once whenever it changes."""
        label = self.label()
        if not self.live and label != self._last_plain:
            self._last_plain = label
            self._write(f"- {label}\n")

    def __enter__(self):
        self._start = time.time()
        if self.live:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join()
            self._write("\r\033[K")


# --- report output ----------------------------------------------------------- #
def format_report(report: ReviewReport, color: bool = False) -> str:
    def paint(code, text):
        return f"{code}{text}{RESET}" if color else text

    ready = report.verdict == "ready"
    verdict = paint(GREEN if ready else RED, report.verdict)
    scores = " · ".join(f"{name} {value}" for name, value in report.criterion_scores.model_dump(exclude_none=True).items())
    lines = [f"{paint(BOLD, f'Score {report.overall_score}/100')}  {verdict}", f"  {paint(DIM, scores)}"]
    if report.failures:
        lines += ["", paint(BOLD, f"Failures ({len(report.failures)})")]
        for failure in report.failures:
            lines += [f"  {paint(RED, '✗')} {failure.id} {paint(DIM, '(' + failure.criterion + ')')}", f"      {failure.reason}"]
    if report.suggested_fixes:
        lines += ["", paint(BOLD, "Suggested fixes")]
        lines += [f"  {i}. {fix}" for i, fix in enumerate(report.suggested_fixes, 1)]
    if ready and not report.failures:
        lines += ["", paint(GREEN, "All checks passed.")]
    return "\n".join(lines)


def friendly_error(exc: Exception) -> str:
    """A short, actionable message instead of a stack trace."""
    text = f"{type(exc).__name__}: {exc}"
    if "429" in text or "RESOURCE_EXHAUSTED" in text or "RateLimit" in text:
        return "The model provider is rate limiting you. Wait a minute and retry, or use a provider with higher limits (MODEL_PROVIDER=nvidia)."
    if "503" in text or "UNAVAILABLE" in text or "overloaded" in text.lower():
        return "The model provider is temporarily unavailable. Retry in a moment."
    if any(token in text for token in ("API key", "api_key", "401", "403", "Authentication", "PERMISSION_DENIED")):
        return "The model rejected the API key. Check GOOGLE_API_KEY or NVIDIA_API_KEY in .env."
    if isinstance(exc, (ValueError, ImportError)):
        return str(exc)
    return f"Review failed ({type(exc).__name__}): {str(exc)[:200]}. Run with --debug for the full trace."


# --- running a review -------------------------------------------------------- #
async def run_review(text: str, progress: Progress, spinner=None, runner_factory=None):
    """Send one request through the team in a fresh session; return the finalizer's message."""
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    if runner_factory is None:
        from readme_reviewer_team.agent import root_agent

        runner_factory = lambda: InMemoryRunner(agent=root_agent, app_name=APP_NAME)  # noqa: E731
    runner = runner_factory()
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id="cli")
    message = types.Content(role="user", parts=[types.Part(text=text)])
    final = None
    async for event in runner.run_async(user_id="cli", session_id=session.id, new_message=message):
        progress.update(event.author, event.is_final_response())
        if spinner:
            spinner.tick()
        if event.author == "report_finalizer" and event.content and event.content.parts:
            final = event.content.parts[0].text
    return final


def review_once(text: str, as_json: bool, debug: bool) -> int:
    progress = Progress()
    try:
        with Spinner(progress.label) as spinner:
            final = asyncio.run(run_review(text, progress, spinner))
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - shown as a friendly message; --debug re-raises
        if debug:
            raise
        print(f"error: {friendly_error(exc)}", file=sys.stderr)
        return 1
    try:
        report = ReviewReport.model_validate_json(final or "")
    except ValueError:
        print(f"error: {final or 'No report was produced.'}", file=sys.stderr)
        return 1
    print(final if as_json else format_report(report, use_color(sys.stdout)))
    return 0 if report.verdict == "ready" else 1


def setup(debug: bool) -> None:
    """Load .env and quiet third-party noise before any agent is imported."""
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT / ".env")
    except ImportError:
        pass
    if not debug:
        warnings.filterwarnings("ignore")
        logging.getLogger("google_adk").setLevel(logging.ERROR)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Review a project folder against the repo's contribution standards.")
    parser.add_argument("folder", nargs="?", help="Folder name or path to review (omit for interactive mode)")
    parser.add_argument("--json", action="store_true", help="print the raw JSON report")
    parser.add_argument("--debug", action="store_true", help="show warnings and full error traces")
    args = parser.parse_args(argv)
    setup(args.debug)

    if args.folder:
        return review_once(f"Review {args.folder}", args.json, args.debug)
    print("README reviewer. Type a folder name or path to review, or 'exit' to quit.", file=sys.stderr)
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return 0
        if line.lower() in {"exit", "quit"}:
            return 0
        if line:
            review_once(line if line.lower().startswith("review") else f"Review {line}", args.json, args.debug)
            print()


if __name__ == "__main__":
    sys.exit(main())
