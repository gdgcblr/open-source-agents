from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.adk.workflow._errors import DynamicNodeFailError
from google.genai.errors import APIError as GenAIAPIError
from litellm.exceptions import APIError as LiteLLMAPIError

if __package__:
    from .core import (
        DEFAULT_MAX_DIFF_BYTES,
        DiffError,
        GitPulseError,
        LintFinding,
        LintStatus,
        ModelReview,
        ModelStatus,
        build_review_prompt,
        fetch_pull_request_head,
        get_branch_diff,
        get_changed_python_files,
        lint_conventional_commit,
        parse_model_review,
        redact_sensitive_values,
        render_report,
        run_gitleaks_git_scanner,
        run_gitleaks_scanner,
        run_ruff_linter,
        scan_diff,
        write_report,
    )
else:
    from core import (
        DEFAULT_MAX_DIFF_BYTES,
        DiffError,
        GitPulseError,
        LintFinding,
        LintStatus,
        ModelReview,
        ModelStatus,
        build_review_prompt,
        fetch_pull_request_head,
        get_branch_diff,
        get_changed_python_files,
        lint_conventional_commit,
        parse_model_review,
        redact_sensitive_values,
        render_report,
        run_gitleaks_git_scanner,
        run_gitleaks_scanner,
        run_ruff_linter,
        scan_diff,
        write_report,
    )


PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")


def run_model_review(
    prompt: str,
    model_name: str | None = None,
    mode: str = "ollama",
) -> ModelReview:
    if __package__:
        from .agent import run_adk_review
    else:
        from agent import run_adk_review

    return parse_model_review(run_adk_review(prompt, model_name, mode=mode))


def _read_diff_file(diff_path: Path, max_bytes: int) -> str:
    try:
        if diff_path.stat().st_size > max_bytes:
            raise DiffError(f"Diff file exceeds the {max_bytes:,}-byte limit.")
        diff_text = diff_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise DiffError("Diff file must be UTF-8 text.") from error
    except OSError as error:
        raise DiffError(f"Could not read diff file {str(diff_path)!r}.") from error
    if not diff_text.strip():
        raise DiffError("Diff file is empty.")
    return diff_text


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review a local branch diff with GitPulse.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    review_parser = subparsers.add_parser("review", help="scan and summarize a branch diff")
    diff_source = review_parser.add_mutually_exclusive_group(required=True)
    diff_source.add_argument("--base", help="base Git ref, for example upstream/main")
    diff_source.add_argument("--diff-file", type=Path, help="read a unified diff from a local file")
    head_source = review_parser.add_mutually_exclusive_group()
    head_source.add_argument(
        "--head-ref",
        help="local branch, tag, or commit to compare (default: current HEAD)",
    )
    head_source.add_argument(
        "--pr-number",
        type=int,
        help="fetch a GitHub pull-request head from the selected remote",
    )
    review_parser.add_argument("--repository", type=Path, default=Path.cwd())
    review_parser.add_argument(
        "--remote",
        default="upstream",
        help="configured Git remote used with --pr-number (default: upstream)",
    )
    review_parser.add_argument(
        "--mode",
        choices=("offline", "ollama", "gemini-api"),
        default="offline",
    )
    review_parser.add_argument(
        "--model",
        help="Ollama or Gemini API model ID; defaults to the matching GITPULSE_*_MODEL setting",
    )
    review_parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_DIR / "PULL_REQUEST_REVIEW.md",
        help="Markdown report path (default: agents/gitpulse/PULL_REQUEST_REVIEW.md)",
    )
    review_parser.add_argument("--overwrite", action="store_true", help="allow replacing the output file")
    review_parser.add_argument(
        "--include-worktree",
        action="store_true",
        help="include staged and unstaged changes to tracked files",
    )
    review_parser.add_argument(
        "--skip-python-lint",
        action="store_true",
        help="skip Ruff checks on changed Python files",
    )
    review_parser.add_argument(
        "--secret-scanner",
        choices=("heuristic", "gitleaks", "both"),
        default="heuristic",
        help="secret scanner backend (default: built-in heuristic)",
    )
    review_parser.add_argument(
        "--gitleaks-path",
        default="gitleaks",
        help="Gitleaks executable path when using the gitleaks backend",
    )
    review_parser.add_argument(
        "--max-diff-bytes",
        type=int,
        default=DEFAULT_MAX_DIFF_BYTES,
        help=f"maximum accepted diff size (default: {DEFAULT_MAX_DIFF_BYTES})",
    )

    commit_parser = subparsers.add_parser(
        "lint-commit",
        help="validate a commit message header against Conventional Commits",
    )
    commit_source = commit_parser.add_mutually_exclusive_group(required=True)
    commit_source.add_argument("--message", help="commit message text")
    commit_source.add_argument("--message-file", type=Path, help="read a commit message from a file")
    return parser


def _lint_commit_message(args: argparse.Namespace) -> int:
    try:
        message = args.message if args.message is not None else args.message_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"GitPulse: could not read the commit message ({type(error).__name__}).", file=sys.stderr)
        return 2

    errors = lint_conventional_commit(message)
    if errors:
        for error in errors:
            print(f"Commit message lint: {error}", file=sys.stderr)
        return 1
    print("Commit message passes Conventional Commits lint.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "lint-commit":
        return _lint_commit_message(args)

    try:
        if args.diff_file:
            if args.head_ref or args.pr_number or args.include_worktree:
                raise DiffError("--head-ref, --pr-number, and --include-worktree require --base.")
            diff_text = _read_diff_file(args.diff_file, args.max_diff_bytes)
            base_ref = f"diff file: {args.diff_file.name}"
        else:
            head_ref = "HEAD"
            if args.pr_number is not None:
                head_ref = fetch_pull_request_head(
                    args.pr_number,
                    args.remote,
                    args.repository,
                )
            elif args.head_ref:
                head_ref = args.head_ref
            diff_text = get_branch_diff(
                args.base,
                args.repository,
                head_ref=head_ref,
                max_bytes=args.max_diff_bytes,
                include_worktree=args.include_worktree,
            )
            base_ref = f"{args.base}...{head_ref}"
            if args.include_worktree:
                base_ref += " (tracked worktree included)"

        findings = []
        if args.secret_scanner in {"heuristic", "both"}:
            findings.extend(scan_diff(diff_text))
        gitleaks_findings = []
        secret_scan_status = "completed"
        secret_scan_note: str | None = None
        if args.secret_scanner in {"gitleaks", "both"}:
            try:
                if args.base and not args.include_worktree:
                    gitleaks_findings = run_gitleaks_git_scanner(
                        args.base,
                        head_ref,
                        args.repository,
                        executable=args.gitleaks_path,
                    )
                else:
                    gitleaks_findings = run_gitleaks_scanner(
                        diff_text,
                        executable=args.gitleaks_path,
                    )
                findings.extend(gitleaks_findings)
            except GitPulseError as error:
                secret_scan_status = "failed"
                secret_scan_note = "Gitleaks did not complete; the dedicated scan is not clean or verified."
                if args.secret_scanner == "both":
                    secret_scan_note += " Built-in heuristic findings are shown separately."
                print(
                    f"GitPulse: Gitleaks failed ({type(error).__name__}); "
                    "the report will still include available findings.",
                    file=sys.stderr,
                )

        lint_findings: list[LintFinding] = []
        lint_status: LintStatus = "skipped"
        lint_note: str | None = None
        if args.skip_python_lint:
            lint_note = "Ruff was skipped by --skip-python-lint."
        elif args.base:
            try:
                changed_python_files = get_changed_python_files(
                    args.base,
                    args.repository,
                    head_ref=head_ref,
                    include_worktree=args.include_worktree,
                )
                if changed_python_files:
                    lint_findings = run_ruff_linter(
                        changed_python_files,
                        args.repository,
                        python_executable=sys.executable,
                    )
                    lint_status = "completed"
                else:
                    lint_note = "No changed Python files were found for Ruff."
            except GitPulseError as error:
                lint_status = "failed"
                lint_note = "Ruff could not complete; deterministic security findings are still included."
                print(
                    f"GitPulse: Ruff check failed ({type(error).__name__}); "
                    "the report will still include security findings.",
                    file=sys.stderr,
                )
        else:
            lint_note = "Ruff was skipped for diff-file input because no worktree paths were assumed."

        review: ModelReview | None = None
        model_status: ModelStatus = "skipped"
        model_note: str | None = None
        if args.mode != "offline":
            if gitleaks_findings:
                model_note = (
                    "AI review was skipped because Gitleaks found possible secrets. "
                    "Resolve or remove them before sending the diff to a model."
                )
            elif secret_scan_status == "failed":
                model_note = "AI review was skipped because the dedicated secret scan did not complete."
            else:
                prompt = build_review_prompt(redact_sensitive_values(diff_text), findings)
                try:
                    review = run_model_review(prompt, args.model, args.mode)
                    model_status = "completed"
                except (
                    GenAIAPIError,
                    LiteLLMAPIError,
                    DynamicNodeFailError,
                    GitPulseError,
                    OSError,
                    RuntimeError,
                    ValueError,
                ) as error:
                    model_status = "failed"
                    print(
                        f"GitPulse: {args.mode} review failed ({type(error).__name__}); "
                        "the report will still include deterministic findings.",
                        file=sys.stderr,
                    )

        report = render_report(
            base_ref,
            findings,
            review,
            model_status=model_status,
            lint_findings=lint_findings,
            lint_status=lint_status,
            lint_note=lint_note,
            secret_scanner=args.secret_scanner,
            secret_scan_status=secret_scan_status,
            secret_scan_note=secret_scan_note,
            model_note=model_note,
        )
        output_path = write_report(report, args.output, overwrite=args.overwrite)
    except (GitPulseError, OSError) as error:
        print(f"GitPulse: {error}", file=sys.stderr)
        return 2

    print(f"Wrote report: {output_path}")
    print(f"Heuristic findings: {len(findings)}")
    if model_status == "failed":
        return 3
    if lint_status == "failed":
        return 4
    if secret_scan_status == "failed":
        return 5
    return 1 if lint_findings or findings else 0


if __name__ == "__main__":
    raise SystemExit(main())