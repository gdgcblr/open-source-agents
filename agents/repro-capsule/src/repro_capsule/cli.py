"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .capsule import load_capsule, make_capsule, repository_revision, save_capsule
from .config import load_project_env
from .model import investigate
from .sandbox import SandboxError, TestResult, run_tests


def demo() -> int:
    """Run a shipped, trusted fixture offline to demonstrate evidence capture."""
    with tempfile.TemporaryDirectory(prefix="repro-capsule-demo-") as temp:
        root = Path(temp)
        (root / "test_demo.py").write_text(
            "import unittest\nclass Demo(unittest.TestCase):\n"
            " def test_expected_behavior(self):\n  self.assertEqual(1 + 1, 3)\n",
            encoding="utf-8",
        )
        # The demo fixture is agent-owned trusted code, never supplied by the target repo.
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-v"], cwd=root,
            capture_output=True, text=True, timeout=10, shell=False, check=False,
        )
        test_result = TestResult(
            "failed" if result.returncode else "passed", result.returncode,
            result.stdout, result.stderr,
            command=("python", "-m", "unittest", "discover", "-v"),
            image=None,
        )
        capsule = make_capsule(root, "Demo fixture: expected 1 + 1 to equal 3", test_result,
                               "The bundled fixture fails as intended; this is a local onboarding demo, not isolated execution.",
                               execution_mode="local_demo")
        print(json.dumps(capsule, indent=2))
        return 0 if test_result.status == "failed" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repro-capsule", description="Investigate and replay Python bug reports safely.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Run the offline, agent-owned evidence-capture demo.")
    sub.add_parser("ui", help="Open the local ReproCapsule dashboard in your browser.")
    run = sub.add_parser("investigate", help="Inspect a repository and optionally run fixed tests in Docker.")
    run.add_argument("--repo", type=Path, required=True)
    run.add_argument("--report", type=Path, required=True)
    run.add_argument("--output", type=Path, default=Path("repro-capsule.json"))
    run.add_argument("--allow-execution", action="store_true", help="Explicitly authorize unittest execution in Docker.")
    replay = sub.add_parser("replay", help="Repeat the fixed test run recorded in a capsule.")
    replay.add_argument("--repo", type=Path, required=True)
    replay.add_argument("--capsule", type=Path, required=True)
    replay.add_argument("--allow-execution", action="store_true", help="Explicitly authorize the Docker test run.")
    replay.add_argument("--allow-revision-mismatch", action="store_true", help="Explicitly allow replay on a different or unverifiable Git revision.")
    return parser


def main() -> int:
    load_project_env()
    args = build_parser().parse_args()
    if args.command == "demo":
        return demo()
    if args.command == "ui":
        from .server import serve

        return serve()
    try:
        if args.command == "investigate":
            repo = args.repo.resolve(strict=True)
            report = args.report.read_text(encoding="utf-8")
            analysis = investigate(report, repo)
            print(analysis)
            if not args.allow_execution:
                print("\nTests not run: pass --allow-execution to authorize fixed Docker unittest discovery.")
                return 0
            result = run_tests(repo, allow_execution=True)
            capsule = make_capsule(repo, report, result, analysis)
            save_capsule(capsule, args.output)
            print(f"\nReproduction status: {result.status}; capsule: {args.output}")
            return 0
        repo = args.repo.resolve(strict=True)
        old = load_capsule(args.capsule)
        recorded_revision = old.get("repository_revision")
        current_revision = repository_revision(repo)
        revision_matches = recorded_revision is not None and current_revision == recorded_revision
        if not revision_matches and not args.allow_revision_mismatch:
            print(json.dumps({
                "replay_status": "blocked_revision_mismatch",
                "recorded_revision": recorded_revision,
                "current_revision": current_revision,
                "hint": "Check out the capsule commit or pass --allow-revision-mismatch to proceed explicitly.",
            }, indent=2))
            return 2
        result = run_tests(repo, allow_execution=args.allow_execution)
        previous = old["execution"]
        same = (previous.get("status"), previous.get("exit_code")) == (result.status, result.exit_code)
        print(json.dumps({
            "replay_status": "matched" if same else "different",
            "revision_status": "matched" if revision_matches else "unverified_or_overridden",
            "previous": previous.get("status"),
            "current": result.status,
            "current_exit_code": result.exit_code,
        }, indent=2))
        return 0 if same else 2
    except (OSError, ValueError, SandboxError, RuntimeError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
