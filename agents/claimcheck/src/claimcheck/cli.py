from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import httpx
import yaml
from dotenv import load_dotenv

from claimcheck.config import Settings
from claimcheck.demo import demo_image, demo_server, fixture_root
from claimcheck.report import build_report, exit_code, write_report
from claimcheck.safety import bounded_body, http_client
from claimcheck.sandbox import SANDBOX_IMAGE, execute
from claimcheck.tools import Audit


def doctor(*, model: bool = False) -> int:
    checks: dict[str, Any] = {
        "python": sys.version.split()[0],
        "uv": shutil.which("uv") or "missing",
        "mise": shutil.which("mise") or "missing (optional; use make directly)",
        "openspec": shutil.which("openspec") or "missing (needed for spec commands)",
        "docker": shutil.which("docker") or "missing",
        "sandbox_image": SANDBOX_IMAGE,
    }
    ready = True
    if shutil.which("docker"):
        info = execute(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=10)
        checks["docker_daemon"] = info.stdout.strip() if not info.returncode else "unavailable"
        image = execute(["docker", "image", "inspect", "--format", "{{.Id}}", SANDBOX_IMAGE])
        checks["sandbox_ready"] = image.returncode == 0
        ready = info.returncode == 0 and image.returncode == 0
    else:
        ready = False
    if model:
        settings = Settings.from_env()
        with (
            http_client() as client,
            client.stream("GET", settings.base_url.rstrip("/") + "/api/tags") as response,
        ):
            response.raise_for_status()
            names = [item["name"] for item in json.loads(bounded_body(response)).get("models", [])]
        checks["model_present"] = settings.model in names
        ready = ready and settings.model in names
    print(json.dumps(checks, indent=2))
    return 0 if ready else 2


def audit_project(audit: Audit, *, agent: bool, output: Path) -> dict[str, Any]:
    commentary = None
    if agent:
        from claimcheck.agent import run_agent

        try:
            commentary = asyncio.run(run_agent(audit, Settings.from_env()))
        except (RuntimeError, ValueError, TimeoutError, httpx.HTTPError) as exc:
            partial = build_report(audit, agent={"text": f"Agent error: {exc}", "error": True})
            write_report(partial, output)
            raise RuntimeError(f"Agent failed; partial evidence saved to {output}: {exc}") from exc
    else:
        audit.verify_all_claims()
    report = build_report(audit, agent=commentary)
    write_report(report, output)
    print(json.dumps(report["summary"], indent=2))
    print(f"Evidence: {output / 'report.json'}")
    print(f"Readable report: {output / 'report.md'}")
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="claimcheck", description="Check project claims against tool-collected evidence."
    )
    commands = result.add_subparsers(dest="command", required=True)
    check = commands.add_parser("audit", help="Audit a project; no model used unless --agent")
    check.add_argument("project", type=Path)
    check.add_argument("--base-url", help="Explicit API target; spec servers are never trusted")
    check.add_argument("--image", help="Already built image to inspect; no automatic pulls/builds")
    check.add_argument(
        "--allow-exec", action="store_true", help="Execute README commands in Docker"
    )
    check.add_argument("--allow-remote-api", action="store_true")
    check.add_argument("--allow-http-api", action="store_true")
    check.add_argument(
        "--agent",
        action="store_true",
        help="Send discovered claim text and evidence to the configured Ollama server",
    )
    check.add_argument("--output", type=Path, default=Path("reports/audit"))
    demo = commands.add_parser("demo", help="Run bundled synthetic lying project")
    demo.add_argument(
        "--docker", action="store_true", help="Exercise image drift and README execution"
    )
    demo.add_argument("--agent", action="store_true", help="Use native Ollama ADK agent")
    demo.add_argument("--output", type=Path, default=Path("reports/demo"))
    health = commands.add_parser("doctor", help="Check dependencies without installing anything")
    health.add_argument("--model", action="store_true", help="Also check approved model endpoint")
    return result


def main() -> int:
    load_dotenv(Path.cwd() / ".env", override=False)
    args = parser().parse_args()
    try:
        if args.command == "doctor":
            return doctor(model=args.model)
        if args.command == "demo":
            with demo_server() as base_url, demo_image(args.docker) as image:
                report = audit_project(
                    Audit(fixture_root(), base_url=base_url, image=image, allow_exec=args.docker),
                    agent=args.agent,
                    output=args.output,
                )
            # The demo succeeds only if it exposes the planted lies and positive controls.
            expected_summary = (
                {"passed": 5, "failed": 8, "not_verified": 0, "error": 0}
                if args.docker
                else {"passed": 2, "failed": 3, "not_verified": 8, "error": 0}
            )
            failed = report["summary"]["failed"]
            if report["summary"] != expected_summary:
                raise RuntimeError(f"Demo expected {expected_summary}, got {report['summary']}")
            print(f"Demo verified: {failed} planted lies detected.")
            return 0
        report = audit_project(
            Audit(
                args.project,
                base_url=args.base_url,
                image=args.image,
                allow_exec=args.allow_exec,
                allow_remote=args.allow_remote_api,
                allow_http=args.allow_http_api,
            ),
            agent=args.agent,
            output=args.output,
        )
        return exit_code(report)
    except (OSError, ValueError, RuntimeError, httpx.HTTPError, yaml.YAMLError) as exc:
        print(f"claimcheck: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
