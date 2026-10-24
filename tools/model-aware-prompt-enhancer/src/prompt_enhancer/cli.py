"""Command-line interface: ``prompt-enhancer <command>`` (or ``python -m prompt_enhancer``)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any
from collections.abc import Callable

from . import __version__, registry, sources
from .analyzer import Options, analyze
from .engine import enhance
from .rules import all_rules
from .schema import SEVERITY_ORDER, AnalysisReport, EnhancementResult, Patch

EXIT_FINDINGS = 1  # analyze --fail-on threshold reached, or eval failures
EXIT_USAGE = 2


# ----------------------------------------------------------------------------- helpers


def _read_inputs(args: argparse.Namespace) -> list[tuple[str, str]]:
    """Return [(name, text)]: --input files, else the positional prompt, else stdin."""
    if getattr(args, "input", None):
        return [(p, Path(p).read_text(encoding="utf-8")) for p in args.input]
    if args.prompt and args.prompt != "-":
        return [("<argument>", args.prompt)]
    if sys.stdin.isatty():
        raise SystemExit("prompt-enhancer: provide a prompt argument, --input FILE, or pipe text on stdin")
    return [("<stdin>", sys.stdin.read())]


def _options(args: argparse.Namespace) -> Options:
    o = Options.from_env()
    if getattr(args, "min_words", None) is not None:
        o.min_words = args.min_words
    o.force = bool(getattr(args, "force", False))
    if getattr(args, "disable", None):
        o.disabled_rules = frozenset(o.disabled_rules | {x.strip() for x in ",".join(args.disable).split(",") if x.strip()})
    if getattr(args, "min_confidence", None) is not None:
        o.min_confidence = args.min_confidence
    return o


def _split(values: list[str] | None) -> list[str]:
    return [x.strip() for v in values or [] for x in v.split(",") if x.strip()]


def _line_col(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    col = offset - (text.rfind("\n", 0, offset) + 1) + 1
    return line, col


def _short(s: str, n: int = 90) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


# ----------------------------------------------------------------------------- rendering


def render_analysis(rep: AnalysisReport, name: str | None = None) -> str:
    out = []
    head = f"{name}: " if name and name not in {"<argument>", "<stdin>"} else ""
    variant = f" [{rep.variant}]" if rep.variant else ""
    out.append(f"{head}{rep.word_count} words, {rep.tokens} tokens ({rep.token_method}) | task: {rep.task_type} ({rep.intent}) | "
               f"profile: {rep.model_profile} v{rep.profile_version}{variant} | model: {rep.model or 'unspecified'}")
    if rep.requirements:
        out.append("\nLocked requirements (kept verbatim by any enhancement):")
        for r in rep.requirements:
            out.append(f"  {r.id:<4} {r.kind:<10} \"{_short(r.text, 80)}\"")
    patches = {p.id: p for p in rep.patches}
    if rep.diagnostics:
        out.append(f"\nDiagnostics ({len(rep.diagnostics)}):")
        for d in rep.diagnostics:
            out.append(f"  {d.severity.upper():<7} {d.rule_id}  {d.message}")
            for e in d.evidence[:2]:
                out.append(f"          evidence: \"{_short(e.text, 70)}\" @{e.start}")
            out.append(f"          fix: {d.remediation}")
            if d.source_url:
                out.append(f"          source: {d.source_url} ({d.evidence_status})")
            for pid in d.patch_ids:
                p = patches[pid]
                tag = "needs your input" if p.needs_input else ("auto" if p.auto else "opt-in")
                out.append(f"          patch {pid} [{tag}]" + (f": {p.question}" if p.question else f": {p.rationale}"))
    else:
        out.append("\nNo issues found.")
    structural = [p for p in rep.patches if p.id.startswith("S.")]
    if structural:
        out.append("\nStructural patches (" + rep.model_profile + "): " + ", ".join(f"{p.id} [{'auto' if p.auto else 'opt-in'}]" for p in structural))
    for w in rep.warnings:
        out.append(f"warning: {w}")
    return "\n".join(out)


def render_enhancement(r: EnhancementResult) -> str:
    lines = [f"status: {r.status}" + (f" ({r.reason})" if r.reason else "")]
    if r.applied:
        lines.append("applied: " + ", ".join(r.applied))
    if r.pending:
        lines.append("pending (use --accept/--answer or --interactive): " + ", ".join(r.pending))
    if r.rejected:
        lines.append("rejected: " + ", ".join(r.rejected))
    lock = "ok" if r.lock.ok else f"FAILED, missing {', '.join(r.lock.missing)}"
    lines.append(f"requirement lock: {lock} ({len(r.lock.preserved)} preserved)")
    for w in r.warnings:
        lines.append(f"warning: {w}")
    return "\n".join(lines)


def sarif(reports: list[tuple[str, str, AnalysisReport]]) -> dict[str, Any]:
    level = {"error": "error", "warning": "warning", "info": "note"}
    rules = [{"id": r.id, "name": r.name, "shortDescription": {"text": r.description}, "properties": {"category": r.category}} for r in all_rules()]
    results = []
    for name, text, rep in reports:
        for d in rep.diagnostics:
            start = d.evidence[0].start if d.evidence else 0
            end = d.evidence[0].end if d.evidence else 0
            sl, sc = _line_col(text, start)
            el, ec = _line_col(text, end)
            results.append({
                "ruleId": d.rule_id, "level": level[d.severity], "message": {"text": f"{d.message} Fix: {d.remediation}"},
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": name}, "region": {"startLine": sl, "startColumn": sc, "endLine": el, "endColumn": ec}}}],
            })
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "model-aware-prompt-enhancer", "version": __version__, "rules": rules}}, "results": results}],
    }


# ----------------------------------------------------------------------------- commands


def cmd_analyze(args: argparse.Namespace) -> int:
    inputs = _read_inputs(args)
    reports = [(n, t, analyze(t, model=args.model, harness=args.harness, options=_options(args))) for n, t in inputs]
    if args.format == "json":
        data = [rep.to_dict() | {"input": n} for n, _, rep in reports]
        print(json.dumps(data[0] if len(data) == 1 else data, indent=2))
    elif args.format == "sarif":
        print(json.dumps(sarif(reports), indent=2))
    else:
        print("\n\n".join(render_analysis(rep, n) for n, _, rep in reports))
    if args.fail_on:
        threshold = SEVERITY_ORDER[args.fail_on]
        if any(SEVERITY_ORDER[d.severity] >= threshold for _, _, rep in reports for d in rep.diagnostics):
            return EXIT_FINDINGS
    return 0


def interactive_review(prompt: str, args: argparse.Namespace, ask: Callable[[str], str] = input) -> tuple[list[str], list[str], dict[str, str]]:
    """Walk the user through each non-automatic patch. Returns (accept, reject, answers)."""
    rep = analyze(prompt, model=args.model, harness=args.harness, options=_options(args))
    accept, reject, answers = [], [], {}
    by_id: dict[str, Patch] = {p.id: p for p in rep.patches}
    diag_for = {pid: d for d in rep.diagnostics for pid in d.patch_ids}
    for pid, p in by_id.items():
        d = diag_for.get(pid)
        header = f"\n[{pid}] {d.message if d else p.rationale}"
        if p.auto:
            if ask(f"{header}\n  automatic change: {p.rationale}\n  keep it? [Y/n] ").strip().lower() in {"n", "no"}:
                reject.append(pid)
            continue
        if p.needs_input:
            ans = ask(f"{header}\n  {p.question}\n  (answer, or Enter to skip) > ").strip()
            if ans:
                answers[pid] = ans
            continue
        preview = _short((p.new + p.suffix) or "(remove text)", 120)
        if ask(f"{header}\n  proposed: {preview}\n  apply? [y/N] ").strip().lower() in {"y", "yes"}:
            accept.append(pid)
    return accept, reject, answers


def cmd_enhance(args: argparse.Namespace) -> int:
    (name, prompt), *rest = _read_inputs(args)
    if rest:
        raise SystemExit("prompt-enhancer: enhance takes one input at a time")
    accept, reject = _split(args.accept), _split(args.reject)
    answers = {}
    for a in args.answer or []:
        if "=" not in a:
            raise SystemExit(f"prompt-enhancer: --answer expects ID=TEXT, got {a!r}")
        k, v = a.split("=", 1)
        answers[k.strip()] = v
    if args.interactive:
        if not sys.stdin.isatty() and name == "<stdin>":
            raise SystemExit("prompt-enhancer: --interactive needs a terminal; pass the prompt with --input or use --accept/--answer")
        a2, r2, ans2 = interactive_review(prompt, args)
        accept += a2
        reject += r2
        answers.update(ans2)
    r = enhance(prompt, model=args.model, harness=args.harness, options=_options(args), accept=accept, reject=reject, answers=answers)
    if args.format == "json":
        payload = json.dumps(r.to_dict(), indent=2)
        if args.output:
            Path(args.output).write_text(payload, encoding="utf-8")
        else:
            print(payload)
        return 0
    body = r.additional_context if r.mode == "augment" else r.enhanced
    if args.output:
        Path(args.output).write_text(body or "", encoding="utf-8")
    if args.diff:
        sys.stdout.write(r.diff or "(no changes)\n")
    elif not args.output:
        sys.stdout.write((body or "") + ("" if (body or "").endswith("\n") else "\n"))
    if args.explain or args.diff or args.output:
        print("\n" + render_enhancement(r), file=sys.stderr)
        if args.explain:
            print("\n" + render_analysis(r.analysis), file=sys.stderr)
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    from .evaluation import compare_to_baseline, load_cases, run_offline
    from .evaluation.report import render_offline

    rep = run_offline(load_cases(args.dataset), model=args.model, harness=args.harness, options=_options(args))
    if args.baseline:
        rep = compare_to_baseline(rep, json.loads(Path(args.baseline).read_text(encoding="utf-8")))
    if args.save:
        Path(args.save).write_text(json.dumps(rep.to_dict(), indent=2), encoding="utf-8")
    print(json.dumps(rep.to_dict(), indent=2) if args.format == "json" else render_offline(rep, markdown=args.format == "markdown"))
    return EXIT_FINDINGS if rep.summary["failed"] or rep.regressions else 0


def cmd_eval_e2e(args: argparse.Namespace) -> int:
    from .evaluation import load_cases
    from .evaluation.e2e import run_e2e
    from .evaluation.providers import get_provider
    from .evaluation.report import render_e2e

    provider = get_provider(args.provider)
    out = run_e2e(load_cases(args.dataset), provider, args.model, trials=args.trials, max_tokens=args.max_tokens, options=_options(args), workers=args.workers)
    if args.save:
        Path(args.save).write_text(json.dumps(out, indent=2), encoding="utf-8")
    if args.report:
        from .evaluation.report import render_e2e_html, render_e2e_markdown

        body = render_e2e_markdown(out) if args.report.endswith(".md") else render_e2e_html(out)
        Path(args.report).write_text(body, encoding="utf-8")
    print(json.dumps(out, indent=2) if args.format == "json" else render_e2e(out))
    return 0


def cmd_profiles(args: argparse.Namespace) -> int:
    models = registry.load_models()
    if args.format == "json":
        from dataclasses import asdict
        print(json.dumps({"models": [asdict(p) for p in models.values()], "harnesses": [asdict(h) for h in registry.load_harnesses().values()]}, indent=2))
        return 0
    for p in sorted(models.values(), key=lambda p: p.id):
        age = (date.today() - date.fromisoformat(p.last_verified)).days
        print(f"{p.id:<18} v{p.profile_version}  verified {p.last_verified} ({age}d ago)  {len(p.guidelines)} guidelines, "
              f"{len(p.variants)} variants  aliases: {', '.join(p.aliases) or '-'}")
        for s in p.sources:
            print(f"{'':<20}{s.url}")
        for v in p.variants:
            print(f"{'':<20}variant {v.id}: {', '.join(v.match)}")
    print("\nharnesses: " + ", ".join(f"{h.id} ({h.mode})" for h in registry.load_harnesses().values()))
    return 0


def cmd_rules(args: argparse.Namespace) -> int:
    rules = all_rules()
    if args.format == "json":
        print(json.dumps([{"id": r.id, "name": r.name, "category": r.category, "severity": r.severity,
                           "tasks": sorted(r.tasks) if r.tasks else None, "description": r.description} for r in rules], indent=2))
        return 0
    for r in rules:
        tasks = ",".join(sorted(r.tasks)) if r.tasks else "all"
        print(f"{r.id}  {r.severity:<7} {r.category:<13} {r.name:<32} [{tasks}]  {r.description}")
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    res = registry.resolve(args.model, registry.get_harness(args.harness))
    print(json.dumps({"model": args.model, "profile": res.profile.id, "version": res.profile.profile_version,
                      "variant": res.profile.variant, "matched": res.matched, "how": res.how}))
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    rows = sources.check(use_cache=not args.no_cache)
    if args.format == "json":
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            if r["status"] == "error":
                print(f"ERROR    {r['url']}\n         {r['error']}")
                continue
            changed = {None: "first check", True: "CHANGED since last check", False: "unchanged"}[r["changed_since_last_check"]]
            print(f"{r['status'].upper():<8} {r['url']}\n         {r['sections_checked']} cited sections, {len(r['missing_sections'])} missing; {changed}")
            for m in r["missing_sections"]:
                print(f"         missing: {m}")
    return 0 if all(r["status"] == "ok" for r in rows) else EXIT_FINDINGS


def cmd_mcp(args: argparse.Namespace) -> int:
    from .mcp_server import serve

    return serve()


def cmd_hook(args: argparse.Namespace) -> int:
    from .adapters import claude_code

    return claude_code.main()


# ----------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="prompt-enhancer", description="Diagnose prompts, propose minimal intent-preserving patches, and measure them. Offline by default.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def model_opts(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--model", "-m", help="model id or alias: claude-sonnet-5, gpt-4.1, o3, gemini-3-pro, or claude/gpt/gemini")
        sp.add_argument("--harness", default="api", help="api | chat | claude-code (default: api)")
        sp.add_argument("--min-words", type=int, default=None, help="no structural changes below this many words (default 8)")
        sp.add_argument("--disable", action="append", help="rule ids to turn off (comma-separated, repeatable)")
        sp.add_argument("--min-confidence", type=float, default=None, help="hide diagnostics below this confidence (0-1)")

    def input_opts(sp: argparse.ArgumentParser, multi: bool) -> None:
        sp.add_argument("prompt", nargs="?", help="prompt text, or '-' for stdin")
        if multi:
            sp.add_argument("--input", "-i", action="append", help="read the prompt from a file (repeatable)")
        else:
            sp.add_argument("--input", "-i", help="read the prompt from a file")

    a = sub.add_parser("analyze", help="diagnose a prompt without changing it")
    input_opts(a, multi=True)
    model_opts(a)
    a.add_argument("--format", "-f", choices=["text", "json", "sarif"], default="text")
    a.add_argument("--fail-on", choices=["info", "warning", "error"], help="exit 1 if any diagnostic is at or above this severity (for CI)")
    a.set_defaults(func=cmd_analyze)

    e = sub.add_parser("enhance", help="apply minimal patches and show the result or a diff")
    input_opts(e, multi=False)
    model_opts(e)
    e.add_argument("--output", "-o", help="write the enhanced prompt (or JSON with --format json) to this file")
    e.add_argument("--diff", action="store_true", help="print a unified diff instead of the enhanced prompt")
    e.add_argument("--format", "-f", choices=["text", "json"], default="text")
    e.add_argument("--accept", action="append", help="patch or rule ids to apply (comma-separated, repeatable; 'all' for every patch not needing input)")
    e.add_argument("--reject", action="append", help="patch or rule ids to skip, including automatic ones like S.wrap")
    e.add_argument("--answer", action="append", metavar="ID=TEXT", help="answer a question patch, e.g. --answer 'PE301=5 bullet points'")
    e.add_argument("--interactive", action="store_true", help="review each patch in the terminal")
    e.add_argument("--force", action="store_true", help="enhance even if no change is recommended (still never invents content)")
    e.add_argument("--explain", action="store_true", help="also print diagnostics to stderr")
    e.set_defaults(func=cmd_enhance)

    ev = sub.add_parser("eval", help="run the offline benchmark on a JSONL dataset")
    ev.add_argument("--dataset", "-d", required=True)
    model_opts(ev)
    ev.add_argument("--format", "-f", choices=["text", "json", "markdown"], default="text")
    ev.add_argument("--baseline", help="previous `eval --save` JSON; reports regressions against it")
    ev.add_argument("--save", help="write the full JSON report here (use as a future baseline)")
    ev.set_defaults(func=cmd_eval)

    x = sub.add_parser("eval-e2e", help="A/B the original vs enhanced prompts through a real model (needs an API key; sends prompts to the provider)")
    x.add_argument("--dataset", "-d", required=True)
    x.add_argument("--provider", required=True, choices=["claude-code", "anthropic", "openai", "gemini", "mock"],
                   help="claude-code uses your Claude Code login (no API key); the others need an API key")
    x.add_argument("--model", "-m", required=True)
    x.add_argument("--trials", type=int, default=1, help="answers per arm per case (default 1)")
    x.add_argument("--max-tokens", type=int, default=1024)
    x.add_argument("--workers", type=int, default=1, help="parallel requests (default 1)")
    x.add_argument("--format", "-f", choices=["text", "json"], default="text")
    x.add_argument("--save", help="write the full JSON results (prompts, answers, per-check results) here")
    x.add_argument("--report", help="write a side-by-side comparison report: .html (viewable page) or .md (for a PR)")
    x.set_defaults(func=cmd_eval_e2e, harness="api", min_words=None, disable=None, min_confidence=None)

    pr = sub.add_parser("profiles", help="list model and harness profiles")
    pr.add_argument("--format", "-f", choices=["text", "json"], default="text")
    pr.set_defaults(func=cmd_profiles)

    ru = sub.add_parser("rules", help="list diagnostic rules")
    ru.add_argument("--format", "-f", choices=["text", "json"], default="text")
    ru.set_defaults(func=cmd_rules)

    r = sub.add_parser("resolve", help="show which profile (and variant) a model id maps to")
    r.add_argument("model")
    r.add_argument("--harness", default="api")
    r.set_defaults(func=cmd_resolve)

    s = sub.add_parser("sources", help="check cited documentation for drift (network, opt-in)")
    s.add_argument("action", choices=["check"])
    s.add_argument("--no-cache", action="store_true", help="do not read or write the fingerprint cache")
    s.add_argument("--format", "-f", choices=["text", "json"], default="text")
    s.set_defaults(func=cmd_sources)

    m = sub.add_parser("mcp", help="run the MCP server on stdio (for Claude Code, Claude Desktop, Cursor and other MCP clients)")
    m.set_defaults(func=cmd_mcp)

    h = sub.add_parser("hook", help="run as a harness hook (reads hook JSON on stdin)")
    h.add_argument("target", choices=["claude-code"])
    h.set_defaults(func=cmd_hook)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "input", None) and isinstance(args.input, str):
        args.input = [args.input]
    try:
        return args.func(args)
    except (KeyError, ValueError, OSError, RuntimeError) as e:  # ProfileError, DatasetError, ProviderError, PatchConflict
        msg = e.args[0] if isinstance(e, KeyError) and e.args else e
        print(f"prompt-enhancer: error: {msg}", file=sys.stderr)
        return EXIT_USAGE
