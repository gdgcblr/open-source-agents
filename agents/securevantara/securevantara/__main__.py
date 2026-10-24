"""CLI: private JSON reports; status reflects execution, never absence of bugs."""
import argparse
import json
import http.client
from datetime import datetime, timezone

from .adapter import authorize, run_xalgorix
from .agent import run_agent
from .checks import check, deduplicate
from .local_llm import review


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["check", "review", "agent", "adk", "xalgorix-info", "xalgorix-review"])
    parser.add_argument("--provider", choices=["ollama", "gemini", "mock"], default="ollama")
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument("--query", default="Review examples/source for security vulnerabilities and suggest remediations")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--no-remediation", action="store_true", default=False)
    parser.add_argument("--source")
    parser.add_argument("--scope")
    parser.add_argument("--authorized", action="store_true")
    parser.add_argument("--sandboxed", action="store_true")
    parser.add_argument("--executable", default="xalgorix")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output-limit", type=int, default=65536)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    try:
        stream = open(args.report, "x", encoding="utf-8", opener=private_file)
    except OSError as exc:
        parser.exit(2, f"cannot create report: {exc}\n")
    report = dict(schema_version="1.0", operation=args.operation, findings=[], errors=[],
                  started_at=datetime.now(timezone.utc).isoformat(),
                  source=args.source, scope=args.scope, authorized=args.authorized)
    try:
        if args.operation == "adk":
            from .adk_agent import run_with_adk
            model = args.model if args.model != "gemma4:e4b" else "gemini-2.5-flash"
            report["adk"] = run_with_adk(query=args.query, model=model)
            if report["adk"].get("status") != "success":
                report["errors"].append("ADK execution failed")
        elif args.operation == "agent":
            if not args.source or not args.scope:
                raise ValueError("--source and --scope required")
            root = authorize(args.source, args.scope, args.authorized)
            model = args.model
            if args.provider == "gemini" and args.model == "gemma4:e4b":
                model = "gemini-2.5-flash"
            elif args.provider == "mock" and args.model == "gemma4:e4b":
                model = "mock-engine"
            agent_output = run_agent(
                root=root,
                provider=args.provider,
                model=model,
                api_key=args.api_key,
                timeout=min(args.timeout, 300),
                remediate=not args.no_remediation
            )
            report["agent"] = agent_output["agent"]
            report["findings"] = agent_output["findings"]
            if agent_output["errors"]:
                report["errors"].extend(agent_output["errors"])
        elif args.operation in {"check", "review"}:
            if not args.source or not args.scope:
                raise ValueError("--source and --scope required")
            root = authorize(args.source, args.scope, args.authorized)
            report["findings"], report["errors"] = check(root)
            if args.operation == "review":
                report["local_llm"] = review(root, args.model, min(args.timeout, 300))
                report["findings"] = deduplicate(report["findings"] + report["local_llm"]["findings"])
                if report["local_llm"]["error"]:
                    report["errors"].append(report["local_llm"]["error"])
        else:
            if args.operation == "xalgorix-review" and (not args.source or not args.scope):
                raise ValueError("--source and --scope required")
            report["xalgorix"] = run_xalgorix(
                args.executable,
                args.source if args.operation == "xalgorix-review" else None,
                args.scope, args.authorized, args.sandboxed,
                args.timeout, args.output_limit)
            if report["xalgorix"].get("error"):
                report["errors"].append(report["xalgorix"]["error"])
    except (ValueError, OSError, http.client.HTTPException) as exc:
        report["errors"].append(str(exc))
    status = 2 if report["errors"] else 0
    report["exit_status"] = status
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    try:
        # Exclusive creation avoids clobbering evidence or following report symlinks.
        with stream:
            json.dump(report, stream, indent=2, ensure_ascii=True)
            stream.write("\n")
    except OSError as exc:
        parser.exit(2, f"cannot create report: {exc}\n")
    return status


def private_file(path, flags):
    import os
    return os.open(path, flags, 0o600)


if __name__ == "__main__":
    raise SystemExit(main())
