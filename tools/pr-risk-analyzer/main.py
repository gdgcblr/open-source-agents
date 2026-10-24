import argparse
import json
import subprocess
import sys
from pathlib import Path

from analyzer import DEFAULT_CONFIG, analyze_files
from diff_parser import parse_unified_diff


SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


def load_config(path: str | None) -> dict:
    if path is None:
        return DEFAULT_CONFIG

    config_path = Path(path)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Cannot read config file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON config: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Config root must be a JSON object.")

    # Merge top-level defaults with provided settings.
    merged = {
        **DEFAULT_CONFIG,
        **data,
        "rules": {
            **DEFAULT_CONFIG["rules"],
            **data.get("rules", {}),
        },
        "thresholds": {
            **DEFAULT_CONFIG["thresholds"],
            **data.get("thresholds", {}),
        },
    }

    if not isinstance(merged["rules"], dict):
        raise ValueError("'rules' must be a JSON object.")
    if not isinstance(merged["thresholds"], dict):
        raise ValueError("'thresholds' must be a JSON object.")
    if not isinstance(merged["sensitive_paths"], list) or not all(
        isinstance(item, str) for item in merged["sensitive_paths"]
    ):
        raise ValueError("'sensitive_paths' must be a list of strings.")

    for name in ("max_changed_files", "max_added_lines"):
        value = merged["thresholds"].get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"threshold '{name}' must be a non-negative integer.")

    for name, value in merged["rules"].items():
        if not isinstance(value, bool):
            raise ValueError(f"rule setting '{name}' must be true or false.")

    return merged


def get_git_diff(repo: str, base: str, head: str) -> str:
    """Run Git safely without shell interpolation."""
    command = [
        "git",
        "-C",
        repo,
        "diff",
        "--no-ext-diff",
        "--no-color",
        "--find-renames",
        "--",
    ]

    # Use the normal revision syntax in a separate invocation.
    command = [
        "git",
        "-C",
        repo,
        "diff",
        "--no-ext-diff",
        "--no-color",
        "--find-renames",
        f"{base}...{head}",
    ]

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise ValueError(
            "Git was not found. Install Git and ensure it is on PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Git diff timed out.") from exc

    if result.returncode != 0:
        # Do not include the complete command or diff in the error.
        message = result.stderr.strip() or "Git could not generate the diff."
        raise ValueError(message)

    return result.stdout


def print_text_report(report) -> None:
    print("\nPR Risk Analyzer")
    print("=" * 50)
    print(f"Files changed : {report.files_changed}")
    print(f"Lines added   : {report.additions}")
    print(f"Lines deleted : {report.deletions}")
    print(f"Findings      : {len(report.findings)}")

    if not report.findings:
        print("\nNo configured risk signals detected.")
        return

    for index, finding in enumerate(report.findings, start=1):
        location = finding.file_path or "<repository>"
        if finding.line_number is not None:
            location += f":{finding.line_number}"

        print(f"\n{index}. [{finding.severity.upper()}] {finding.title}")
        print(f"   Rule: {finding.rule_id}")
        print(f"   File: {location}")
        print(f"   {finding.message}")

        if finding.evidence:
            print(f"   Evidence: {finding.evidence}")

        if finding.recommendation:
            print(f"   Recommendation: {finding.recommendation}")

        print(f"   Confidence: {finding.confidence}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze Git diffs for potential PR review risks."
    )

    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument(
        "--diff-file",
        help="Path to a unified diff file.",
    )
    source.add_argument(
        "--repo",
        help="Path to a local Git repository.",
    )

    parser.add_argument("--base", help="Base Git ref; used with --repo.")
    parser.add_argument("--head", help="Head Git ref; used with --repo.")
    parser.add_argument(
        "--config",
        help="Path to a JSON configuration file.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Report format.",
    )
    parser.add_argument(
        "--output",
        help="Optional file path for the report.",
    )
    parser.add_argument(
        "--fail-on",
        choices=("critical", "high", "medium", "low", "info", "never"),
        default="never",
        help="Return exit code 1 if any finding meets this severity threshold.",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Print the default configuration and exit.",
    )

    args = parser.parse_args()

    if args.show_config:
        print(json.dumps(DEFAULT_CONFIG, indent=2))
        return 0

    if not args.diff_file and not args.repo:
        parser.error("Provide either --diff-file or --repo.")

    if args.repo and not (args.base and args.head):
        parser.error("--repo requires both --base and --head.")

    if (args.base or args.head) and not args.repo:
        parser.error("--base and --head can only be used with --repo.")

    try:
        config = load_config(args.config)

        if args.diff_file:
            diff_text = Path(args.diff_file).read_text(encoding="utf-8")
        else:
            diff_text = get_git_diff(args.repo, args.base, args.head)

        files = parse_unified_diff(diff_text)
        report = analyze_files(files, config)

        if args.format == "json":
            rendered = json.dumps(report.to_dict(), indent=2)
        else:
            # Capture the text report for optional output-file writing too.
            from io import StringIO
            from contextlib import redirect_stdout

            buffer = StringIO()
            with redirect_stdout(buffer):
                print_text_report(report)
            rendered = buffer.getvalue()

        if args.output:
            Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)

        if args.fail_on != "never":
            threshold = SEVERITY_ORDER[args.fail_on]
            if any(
                SEVERITY_ORDER[finding.severity] <= threshold
                for finding in report.findings
            ):
                return 1

        return 0

    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())