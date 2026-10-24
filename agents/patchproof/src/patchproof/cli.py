"""Command-line interface for PatchProof."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from patchproof.config import PatchProofConfig
from patchproof.core.enums import ExecutionMode, ModelMode, SourceKind
from patchproof.core.models import RunInput
from patchproof.orchestration.pipeline import PatchProofOrchestrator
from patchproof.reporting.composer import ReportComposer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="patchproof",
        description="PatchProof: Evidence-driven, multi-agent software-change verification.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo_parser = subparsers.add_parser(
        "demo",
        help="Run a verification workflow on a checked-in local fixture.",
    )
    demo_parser.add_argument(
        "--fixture",
        default="retry-limit-bug",
        help="Fixture identifier under fixtures/ (default: retry-limit-bug)",
    )
    demo_parser.add_argument(
        "--mode",
        choices=["deterministic", "provider"],
        default="deterministic",
        help="Model execution mode (default: deterministic)",
    )
    demo_parser.add_argument(
        "--execution-mode",
        choices=["static_only", "sandbox_if_available"],
        default="static_only",
        help="Check execution mode (default: static_only)",
    )
    demo_parser.add_argument(
        "--format",
        choices=["markdown", "json", "both"],
        default="markdown",
        help="Output format printed to stdout (default: markdown)",
    )
    demo_parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional file path to write JSON report",
    )
    demo_parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help="Optional file path to write Markdown report",
    )
    demo_parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=None,
        help="Optional override path for fixtures directory",
    )

    gh_parser = subparsers.add_parser(
        "github",
        help="Run a read-only verification workflow on a public GitHub Pull Request URL.",
    )
    gh_parser.add_argument(
        "--pr-url",
        required=True,
        help="Public GitHub Pull Request URL (https://github.com/<owner>/<repo>/pull/<number>)",
    )
    gh_parser.add_argument(
        "--mode",
        choices=["deterministic", "provider"],
        default="deterministic",
        help="Model execution mode (default: deterministic)",
    )
    gh_parser.add_argument(
        "--execution-mode",
        choices=["static_only", "sandbox_if_available"],
        default="static_only",
        help="Check execution mode (default: static_only)",
    )
    gh_parser.add_argument(
        "--format",
        choices=["markdown", "json", "both"],
        default="markdown",
        help="Output format printed to stdout (default: markdown)",
    )
    gh_parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional file path to write JSON report",
    )
    gh_parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help="Optional file path to write Markdown report",
    )

    ui_parser = subparsers.add_parser(
        "ui",
        help="Launch the PatchProof Architecture & Live Verification Web UI.",
    )
    ui_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host for the web server (default: 127.0.0.1)",
    )
    ui_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Bind port for the web server (default: 8000)",
    )
    ui_parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=None,
        help="Optional override path for fixtures directory",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "ui":
        import uvicorn

        from patchproof.api.app import create_app

        config = PatchProofConfig.from_env(fixtures_dir=args.fixtures_dir)
        app = create_app(config=config)
        sys.stdout.write(
            f"PatchProof Verification Studio running at http://{args.host}:{args.port}\n"
        )
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
        return 0

    if args.command in {"demo", "github"}:
        fixtures_dir = getattr(args, "fixtures_dir", None)
        config = PatchProofConfig.from_env(fixtures_dir=fixtures_dir)
        if args.command == "demo":
            run_input = RunInput(
                source=SourceKind.FIXTURE,
                fixture_id=args.fixture,
                execution_mode=ExecutionMode(args.execution_mode),
                model_mode=ModelMode(args.mode),
            )
        else:
            run_input = RunInput(
                source=SourceKind.GITHUB,
                pull_request_url=args.pr_url,
                execution_mode=ExecutionMode(args.execution_mode),
                model_mode=ModelMode(args.mode),
            )
        orchestrator = PatchProofOrchestrator(config=config)
        composer = ReportComposer()

        report = orchestrator.execute(run_input)
        json_text = composer.render_json(report)
        md_text = composer.render_markdown(report)

        if args.output_json is not None:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(json_text, encoding="utf-8")
        if args.output_md is not None:
            args.output_md.parent.mkdir(parents=True, exist_ok=True)
            args.output_md.write_text(md_text, encoding="utf-8")

        if args.format == "json":
            sys.stdout.write(json_text + "\n")
        elif args.format == "both":
            sys.stdout.write(md_text + "\n---\n" + json_text + "\n")
        else:
            sys.stdout.write(md_text)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
