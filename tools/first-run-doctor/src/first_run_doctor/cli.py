"""Command-line entrypoint; inspecting never executes the target."""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

from . import __version__
from .contract import DoctorError, read_json
from .engine import check_project, exit_code
from .privacy import Redactor
from .report import compare, summary, write_reports


def demo(output):
    """Run packaged trusted examples through exactly the same verification engine."""
    reports = {}
    destination = Path(output)
    if destination.exists():
        raise DoctorError("Demo output directory already exists; choose a fresh directory")
    for name in ("missing-config", "false-success", "invalid-output", "working"):
        env = dict(os.environ)
        env.pop("APP_MODE", None)
        report = check_project(
            files("first_run_doctor").joinpath("fixtures", name), execute=True, environment=env
        )
        reports[name] = report
        write_reports(report, destination / name)
    result = {
        "schema_version": 1,
        "synthetic_fixtures": True,
        "cases": {name: report["verification"] for name, report in reports.items()},
        "comparison": compare(reports["false-success"], reports["working"]),
    }
    expected = {
        "missing-config": "unknown",
        "false-success": "failed",
        "invalid-output": "failed",
        "working": "verified",
    }
    (destination / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print("FIRST RUN DOCTOR / OFFLINE DEMO")
    for name, report in reports.items():
        print(f"{name:18} {report['verification'].upper()}")
    print("Retest: " + result["comparison"]["note"])
    print("Reports: " + str(destination))
    return 0 if result["cases"] == expected and result["comparison"]["comparable"] else 1


def parser():
    root = argparse.ArgumentParser(
        description="Verify that a local Python example creates its promised output."
    )
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="operation", required=True)
    for name in ("inspect", "check"):
        command = commands.add_parser(
            name, help="Preview checks" if name == "inspect" else "Check a declared example"
        )
        command.add_argument("project", type=Path)
        command.add_argument(
            "--contract", default="doctor.json", help="Contract path relative to project"
        )
        command.add_argument(
            "--python", help="Absolute Python executable (default: this interpreter)"
        )
        command.add_argument("--format", choices=("text", "json"), default="text")
        command.add_argument(
            "--output-dir", type=Path, help="New report directory, outside the target project"
        )
        if name == "check":
            command.add_argument(
                "--execute",
                action="store_true",
                help="Execute trusted local code as your OS user (not a sandbox)",
            )
            command.add_argument(
                "--diagnose", choices=("jev",), help="Explicitly send redacted evidence to Jev"
            )
            command.add_argument(
                "--jev-env-file", type=Path, help="Explicit local .env containing the Jev key"
            )
    comparison = commands.add_parser("compare", help="Compare two JSON reports")
    comparison.add_argument("before", type=Path)
    comparison.add_argument("after", type=Path)
    comparison.add_argument("--format", choices=("text", "json"), default="text")
    example = commands.add_parser(
        "demo", help="Execute four bundled trusted examples without API keys"
    )
    example.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".doctor-reports")
        / ("demo-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")),
    )
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    redactor = Redactor(os.environ)
    try:
        if args.operation == "demo":
            return demo(args.output_dir)
        if args.operation == "compare":
            result = redactor.object(compare(read_json(args.before), read_json(args.after)))
            if args.format == "json":
                print(json.dumps(result, indent=2))
            else:
                print(result["note"])
                print(f"{result['before'].upper()} -> {result['after'].upper()}")
                for check in result["checks"]:
                    print(f"{check['id']}: {check['before']} -> {check['after']}")
            return 0 if result["comparable"] else 3
        execute = getattr(args, "execute", False)
        if getattr(args, "diagnose", None) and not execute:
            raise DoctorError("--diagnose requires --execute; preview makes no network request")
        if args.output_dir:
            if args.output_dir.resolve().is_relative_to(args.project.resolve()):
                raise DoctorError("Report directory must be outside the target project")
            if args.output_dir.exists() or args.output_dir.is_symlink():
                raise DoctorError("Report directory already exists; choose a fresh directory")
        report = check_project(
            args.project,
            contract_name=args.contract,
            execute=execute,
            python=args.python,
            diagnose=bool(getattr(args, "diagnose", None)),
            env_file=getattr(args, "jev_env_file", None),
        )
        if args.output_dir:
            write_reports(report, args.output_dir)
        print(json.dumps(report, indent=2) if args.format == "json" else summary(report))
        return exit_code(report) if execute else 0
    except (DoctorError, OSError, ValueError, KeyError, TypeError) as exc:
        message = redactor.text(str(exc))
        if getattr(args, "format", None) == "json":
            print(json.dumps({"error": message, "verification": "unknown"}))
        else:
            print("FirstRun Doctor: " + message, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("FirstRun Doctor: interrupted; completion unverified", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
