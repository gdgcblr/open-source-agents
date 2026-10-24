"""rce-sentinel command line."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from rce_sentinel import gitio, hooks, report
from rce_sentinel.config import load_settings
from rce_sentinel.engine import Scanner, collect_staged, collect_tree


def _root(path: str | None) -> tuple[Path, bool]:
    start = Path(path or ".").resolve()
    try:
        return gitio.repo_root(start), True
    except RuntimeError:
        return start, False


def cmd_install_hooks(args: argparse.Namespace) -> int:
    root, is_git = _root(args.repo)
    if not is_git:
        print("not a git repository", file=sys.stderr)
        return 2
    for line in hooks.install(root):
        print(line)
    return 0


def _run(root: Path, is_git: bool, mode: str, as_json: bool, live: bool = False) -> int:
    settings = load_settings(root)
    scanner = Scanner(settings)
    if live:
        from rce_sentinel.trace import live_printer

        scanner.emit = live_printer(sys.stderr)
    budget = None
    if mode == "pre-commit":
        files = collect_staged(root)
        budget = float(settings.policy.get("pre_commit_budget_seconds", 10))
    else:
        files = collect_tree(root, use_git=is_git)
    commit = gitio.head_sha(root) if is_git else ""
    rep = scanner.scan(files, mode, wall_seconds=budget, commit=commit)
    jpath, mpath = report.write(rep, settings.state_dir)
    if as_json:
        print(rep.model_dump_json(indent=2))
    else:
        report.terminal(rep)
        print(f"  reports: {jpath} and {mpath}", file=sys.stderr)
    return 1 if rep.blocked else 0


def cmd_scan(args: argparse.Namespace) -> int:
    root, is_git = _root(args.repo)
    mode = "pre-commit" if args.staged else "full"
    if args.staged and not is_git:
        print("--staged needs a git repository", file=sys.stderr)
        return 2
    return _run(root, is_git, mode, args.json, args.live)


def cmd_hook(args: argparse.Namespace) -> int:
    root, is_git = _root(None)
    if args.name == "pre-commit":
        return _run(root, is_git, "pre-commit", False)
    _run(root, is_git, args.name, False)  # post-commit / post-merge never block
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    from rce_sentinel.intel.agent import IntelAgent, load_simulated

    root, _ = _root(args.repo)
    settings = load_settings(root)
    agent = IntelAgent(Scanner(settings))
    simulated = load_simulated(args.simulate) if args.simulate else None
    interval = float(settings.sources.get("poll_interval_minutes", 30)) * 60
    while True:
        res = agent.run_once(simulated)
        print(f"intel: fetched {res.fetched}, new {res.new}, rce {res.rce}, "
              f"matched {res.matched}")
        for e in res.errors:
            print(f"  ! {e}")
        for n in res.notices:
            print(f"  ! {n}")
        for r in res.realerts:
            print(f"  re-alert: {r}")
        for p in res.proposals:
            print(f"  draft mitigation (not applied, not pushed): {p}")
        for n in res.notified:
            print(f"  notified: {n}")
        if args.once or simulated is not None:
            return 0
        time.sleep(interval)


def cmd_trace(args: argparse.Namespace) -> int:
    import os

    from rce_sentinel import trace as tr

    if args.text == "-":
        text = sys.stdin.read()
    elif args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        print("give code as an argument, --file FILE, or '-' for stdin", file=sys.stderr)
        return 2
    os.environ.setdefault("RCE_SENTINEL_PROVIDER", "hybrid" if not args.real_only else "auto")
    state = Path(args.state).resolve()
    seed = Path(args.osv_seed) if args.osv_seed else None
    if args.show_io:
        os.environ["RCE_SENTINEL_TRACE_IO"] = "1"
    print(tr.run(text, args.lang, state, args.req or [], seed, args.show_io,
                 live=not args.no_live))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Real one-line call to every configured model, so a demo never meets a surprise."""
    import time

    import httpx

    from rce_sentinel.orchestrator.llm import ModelRegistry, OpenAICompatProvider

    root, _ = _root(args.repo)
    settings = load_settings(root)
    reg = ModelRegistry(settings.models, "auto")
    prov = OpenAICompatProvider(reg, retries=0)
    bad = 0
    print(f"{'tier':<6} {'model':<28} {'status':<8} detail")
    for tier, specs in reg.all.items():
        for spec in specs:
            if not reg.is_available(spec):
                p = reg.providers.get(spec.provider, {})
                why = (f"not running or model not pulled ({reg.base_url(spec.provider)})"
                       if p.get("local") else f"no key ({p.get('api_key_env')})")
                print(f"{tier:<6} {spec.id:<28} {'skip':<8} {why}")
                continue
            t0 = time.monotonic()
            try:
                r = prov.complete(spec, "Reply with a JSON object only.",
                                  'Reply with {"ok": true}', max_tokens=16, timeout=args.timeout)
                ok = '"ok"' in r.text.replace(" ", "") or "true" in r.text
                print(f"{tier:<6} {spec.id:<28} {'ok' if ok else 'odd':<8} "
                      f"{(time.monotonic() - t0) * 1000:.0f} ms")
                bad += 0 if ok else 1
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                from rce_sentinel.orchestrator.router import STATUS_REASON

                print(f"{tier:<6} {spec.id:<28} {'FAIL':<8} HTTP {code}: "
                      f"{STATUS_REASON.get(code, 'error')}")
                bad += 1
            except Exception as exc:
                print(f"{tier:<6} {spec.id:<28} {'FAIL':<8} {type(exc).__name__}")
                bad += 1
    return 1 if bad else 0


def cmd_cost_report(args: argparse.Namespace) -> int:
    from rce_sentinel.costreport import gather, render
    from rce_sentinel.memory.store import Store
    from rce_sentinel.orchestrator.llm import ModelRegistry

    root, _ = _root(args.repo)
    settings = load_settings(root)
    data = gather(Store(settings.db_path), ModelRegistry(settings.models, "off"), args.last)
    print(json.dumps(data, indent=2, default=str) if args.json else render(data))
    return 0


def cmd_cache(args: argparse.Namespace) -> int:
    from rce_sentinel.memory.store import Store

    root, _ = _root(args.repo)
    settings = load_settings(root)
    n = Store(settings.db_path).cache_clear()
    print(f"cleared {n} cached verdict(s); facts and call history kept")
    return 0


def cmd_osv_import(args: argparse.Namespace) -> int:
    from rce_sentinel.memory.store import Store
    from rce_sentinel.scanner.osv import OsvClient

    root, _ = _root(args.repo)
    settings = load_settings(root)
    records = json.loads(Path(args.file).read_text())
    n = OsvClient(Store(settings.db_path), None, {}).import_seed(records)
    print(f"imported {n} OSV record(s) into the local cache")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rce-sentinel",
                                description="Cost-aware RCE scanner and intel agent")
    p.add_argument("--repo", help="repository path (default: current directory)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("install-hooks", help="install pre-commit, post-commit, post-merge hooks")
    s = sub.add_parser("scan", help="scan the full tree, or the staged diff with --staged")
    s.add_argument("--staged", action="store_true")
    s.add_argument("--json", action="store_true")
    s.add_argument("--live", action="store_true",
                   help="print progress as it happens (which tool fired, which model is asked)")
    h = sub.add_parser("hook", help=argparse.SUPPRESS)
    h.add_argument("name", choices=list(hooks.HOOKS))
    w = sub.add_parser("watch", help="run the zero-day intel agent")
    w.add_argument("--once", action="store_true")
    w.add_argument("--simulate", help="JSON file of intel items to inject instead of polling")
    t = sub.add_parser("trace", help="run one prompt (code snippet) and show the pipeline")
    t.add_argument("text", nargs="?", help="code to review, or '-' to read stdin")
    t.add_argument("--file", help="read the code from a file")
    t.add_argument("--lang", choices=["py", "js", "ts", "go"], help="default: auto-detect")
    t.add_argument("--req", action="append", help="add a pinned dependency, e.g. PyYAML==5.3")
    t.add_argument("--no-live", action="store_true",
                   help="skip the live progress log, print only the final summary")
    t.add_argument("--show-io", action="store_true",
                   help="print the exact prompt sent to each model and its raw reply")
    t.add_argument("--osv-seed", help="OSV records JSON to load (offline advisories)")
    t.add_argument("--state", default=".rce-sentinel-trace",
                   help="persistent state dir (cache, memory, signed verdicts)")
    t.add_argument("--real-only", action="store_true",
                   help="never fall back to the labelled mock provider")
    d = sub.add_parser("doctor", help="make a real call to every configured model")
    d.add_argument("--timeout", type=float, default=60.0)
    c = sub.add_parser("cost-report", help="tokens and dollars per tier vs baseline")
    c.add_argument("--last", type=int, help="only the last N runs")
    c.add_argument("--json", action="store_true")
    cache = sub.add_parser("cache", help="manage the verdict cache")
    cache.add_argument("action", choices=["clear"])
    o = sub.add_parser("osv-import", help="load OSV records into the offline cache")
    o.add_argument("file")
    return p


HANDLERS = {"install-hooks": cmd_install_hooks, "scan": cmd_scan, "hook": cmd_hook,
            "watch": cmd_watch, "trace": cmd_trace, "doctor": cmd_doctor,
            "cost-report": cmd_cost_report, "cache": cmd_cache, "osv-import": cmd_osv_import}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for sub in ("repo",):
        if getattr(args, sub, None) is None:
            setattr(args, sub, None)
    return HANDLERS[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
