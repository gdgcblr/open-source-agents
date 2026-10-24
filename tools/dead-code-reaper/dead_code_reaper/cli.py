"""Command-line interface: scan, run, apply."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__, state
from .ai import annotate, detect_provider
from .analyzer import guess_mode, scan
from .report import build_patch, report_data, summary_lines, write_html, write_json
from .verifier import check_selection, hold_dependencies, keep_closure, verify

OUT_DIR = "reaper-out"


def load_dotenv(path: Path = Path(".env")):
    """Load KEY=value lines from ./.env without overriding existing variables."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def resolve_mode(args, root: Path) -> str:
    if args.app:
        return "app"
    if args.library:
        return "library"
    guess, why = guess_mode(root)
    if sys.stdin.isatty() and sys.stdout.isatty():
        default = "A" if guess == "app" else "L"
        print("Is this project an application or a library that other projects install?")
        print(f"  (guess: {'application' if guess == 'app' else 'library'}, because {why})")
        answer = input(f"  [A]pplication / [L]ibrary [{default}]: ").strip().upper() or default
        return "library" if answer.startswith("L") else "app"
    print("Not running in a terminal and no --app/--library given: assuming library mode, "
          "which keeps every public name. Pass --app to change this.")
    return "library"


def out_dir(args, root: Path) -> Path:
    return Path(args.out).resolve() if args.out else root / OUT_DIR


def cmd_scan(args) -> int:
    root = Path(args.path).resolve()
    mode = resolve_mode(args, root)
    result = scan(root, mode=mode, excludes=args.exclude)
    state.number_removals(result.removals)
    print(f"Scanned {result.files_scanned} files in {mode} mode.")
    for line in summary_lines(result.removals, result.test_only):
        print(line)
    for err in result.parse_errors:
        print(f"  skipped (could not parse): {err}")
    out = out_dir(args, root)
    out.mkdir(parents=True, exist_ok=True)
    data = report_data(project=root.name, root_arg=args.path, mode=mode, readonly=True,
                       check_mode=None, runs=0, ai=None, removals=result.removals,
                       test_only=result.test_only, protected_count=len(result.protected),
                       files_scanned=result.files_scanned, sources=result.sources)
    write_html(out / "report.html", data)
    write_json(out / "report.json", data)
    if args.verbose:
        for r in result.removals:
            print(f"  #{r.number:<3} {r.path}:{r.start:<5} {r.kind:<11} {r.name}  (confidence {r.confidence})")
    print(f"Report: {out / 'report.html'}")
    return 0


def cmd_run(args) -> int:
    root = Path(args.path).resolve()
    mode = resolve_mode(args, root)
    result = scan(root, mode=mode, excludes=args.exclude)
    print(f"Scanned {result.files_scanned} files in {mode} mode: "
          f"{len(result.removals)} candidates, {len(result.test_only)} test-only, "
          f"{len(result.protected)} protected.")
    out = out_dir(args, root)
    if not result.removals:
        print("No dead code found.")
    verified = verify(result, test_cmd=args.test_cmd, timeout=args.timeout,
                      max_runs=args.max_test_runs, log=print)
    if not verified.baseline_passed:
        print(verified.baseline_output)
        return 2
    print(f"Checked in {verified.runs} runs ({verified.seconds:.1f}s).")
    selectable = state.number_removals(result.removals)

    provider = None if args.no_ai else detect_provider()
    ai_label = None
    if provider and selectable:
        ai_label = f"{provider.name} ({provider.model})"
        print(f"AI notes on: sending code snippets of {len(selectable)} removals to {ai_label}. "
              "Use --no-ai to turn this off.")
        noted = annotate(selectable, result, provider, log=print)
        print(f"  AI notes added to {noted} of {len(selectable)} removals.")
        hold_dependencies(result.removals)  # risk warnings may have changed what starts kept

    out.mkdir(parents=True, exist_ok=True)
    data = report_data(project=root.name, root_arg=args.path, mode=mode, readonly=False,
                       check_mode=verified.check_mode, runs=verified.runs, ai=ai_label,
                       removals=result.removals, test_only=result.test_only,
                       protected_count=len(result.protected), files_scanned=result.files_scanned,
                       sources=result.sources)
    write_html(out / "report.html", data)
    write_json(out / "report.json", data)
    state.save(out, root=str(root), root_arg=args.path, mode=mode, check_mode=verified.check_mode,
               test_cmd=args.test_cmd, timeout=args.timeout, sources=result.sources,
               removals=result.removals)
    for line in summary_lines(result.removals, result.test_only):
        print(line)
    print(f"Report: {out / 'report.html'}")
    if selectable:
        print("Review it, then copy the command at the bottom of the report, or run:")
        print(f"  dead-code-reaper apply {args.path}")
    return 0


def cmd_apply(args) -> int:
    root = Path(args.path).resolve()
    out = out_dir(args, root)
    try:
        saved = state.load(out)
        removals = saved["removals"]
        kept = state.parse_keep(args.keep, removals)
    except state.StateError as exc:
        print(exc)
        return 2
    sources, changed = state.read_sources(Path(saved["root"]), saved["hashes"])
    if changed:
        print("These files changed since `run`, so its results no longer apply:")
        for rel in changed[:20]:
            print(f"  {rel}")
        print("Run `dead-code-reaper run` again.")
        return 2

    selectable = [r for r in removals if r.number]
    not_selectable = {r.key for r in removals if not r.number}
    full_keep, why = keep_closure(removals, kept | not_selectable)
    by_key = {r.key: r for r in removals}
    for key, cause in sorted(why.items()):
        if by_key[key].number and key not in kept:
            c = by_key[cause]
            print(f"  also keeping #{by_key[key].number} {by_key[key].name}: "
                  f"used by {('#' + str(c.number)) if c.number else c.name}, which is kept")
    selection = [r for r in selectable if r.key not in full_keep]
    if not selection:
        print("Nothing to remove with this selection.")
        return 0
    lines = sum(r.lines for r in selection)
    label = "tests" if saved["check_mode"] == "tests" else "compile and import check"
    print(f"Checking {len(selection)} removals ({lines} lines) with the {label}...")
    ok, output, new_files = check_selection(saved["root"], sources, selection, saved["check_mode"],
                                            saved["test_cmd"], saved["timeout"])
    if not ok:
        print(output)
        print("The check failed with this selection, so nothing was changed. "
              "Keep more removals, or run again.")
        return 1
    patch = build_patch(sources, new_files)
    out.mkdir(parents=True, exist_ok=True)
    (out / "applied.patch").write_text(patch, encoding="utf-8")
    if args.dry_run:
        print(f"Check passed. Dry run: no files changed. Patch: {out / 'applied.patch'}")
        return 0
    project = Path(saved["root"])
    for rel, text in new_files.items():
        path = project / rel
        if text is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(text, encoding="utf-8")
    deleted = sum(1 for t in new_files.values() if t is None)
    print(f"Check passed. Removed {len(selection)} pieces of dead code ({lines} lines) in "
          f"{len(new_files)} files{f', {deleted} deleted' if deleted else ''}.")
    print(f"Patch saved to {out / 'applied.patch'} (undo with: git apply -R <patch>)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dead-code-reaper",
                                description="Find dead Python code, prove it's safe to delete, and remove it.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp, project_mode=True):
        sp.add_argument("path", help="project directory")
        sp.add_argument("--out", help=f"output directory (default: <path>/{OUT_DIR})")
        if project_mode:
            g = sp.add_mutually_exclusive_group()
            g.add_argument("--app", action="store_true", help="treat the project as an application")
            g.add_argument("--library", action="store_true",
                           help="treat the project as a library: public names are never dead")
            sp.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                            help="skip paths matching this pattern (repeatable)")

    s = sub.add_parser("scan", help="find dead code by reading the project (changes nothing)")
    common(s)
    s.add_argument("-v", "--verbose", action="store_true", help="list every finding")
    s.set_defaults(func=cmd_scan)

    r = sub.add_parser("run", help="find dead code, prove removals against the tests, write the report")
    common(r)
    r.add_argument("--test-cmd", help="command that runs the tests (default: python -m pytest -q -x)")
    r.add_argument("--timeout", type=int, default=600, help="seconds allowed per test run (default 600)")
    r.add_argument("--max-test-runs", type=int, default=60, help="cap on test runs (default 60)")
    r.add_argument("--no-ai", action="store_true", help="don't send code to an AI provider this run")
    r.set_defaults(func=cmd_run)

    a = sub.add_parser("apply", help="remove the selected dead code after one final check")
    common(a, project_mode=False)
    a.add_argument("--keep", help="removals to keep: numbers, ranges, files, or names, e.g. '2,5-7,pricing.py'. "
                                  "Default: keep what the report leaves unticked.")
    a.add_argument("--dry-run", action="store_true", help="check and write the patch, but change no files")
    a.set_defaults(func=cmd_apply)
    return p


def main(argv=None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:  # output piped into e.g. `head`, which closed early
        sys.stderr.close()
        return 0
