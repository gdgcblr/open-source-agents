"""Command-line interface.

  mergewarden review <PR-URL | path>   review one contribution
  mergewarden triage <owner/repo>      review every open PR -> HTML board
  mergewarden fix <path> [--apply]     plan / apply fixes for your own contribution

Exit codes: 0 ready, 1 changes requested, 2 blocked (usable as a CI gate).
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

from google.adk.runners import InMemoryRunner
from google.genai import types

from . import agent as gk
from . import report as render
from .models import Verdict
from .source import PR_RX, github_api

EXIT = {Verdict.READY: 0, Verdict.CHANGES_REQUESTED: 1, Verdict.BLOCKED: 2}


def _log(msg: str, quiet: bool = False) -> None:
    if not quiet:
        print(msg, file=sys.stderr, flush=True)


async def _run(target: str, use_llm: bool, run_setup: bool, project: str | None, quiet: bool,
               model: str | None = None):
    pipeline = gk.build(use_llm=use_llm, model=model or gk.MODEL)
    runner = InMemoryRunner(agent=pipeline, app_name="mergewarden")
    session = await runner.session_service.create_session(
        app_name="mergewarden", user_id="cli",
        state={"target": target, "run_setup": run_setup, "project": project},
    )
    msg = types.Content(role="user", parts=[types.Part(text=target)])
    seen = set()
    try:
        async for ev in runner.run_async(user_id="cli", session_id=session.id, new_message=msg):
            if ev.author not in seen and ev.author != "user":
                seen.add(ev.author)
                _log(f"  ▸ {ev.author}", quiet)
    finally:
        live = gk._LIVE.pop(session.id, {})
    if "report" not in live:
        raise RuntimeError("pipeline finished without a report")
    return live["report"]


def review(target: str, use_llm: bool, run_setup: bool = False, project: str | None = None, quiet: bool = False):
    _log(f"Reviewing {target} ({'Gemini + deterministic' if use_llm else 'deterministic only'})", quiet)
    if not use_llm:
        return asyncio.run(_run(target, False, run_setup, project, quiet))
    for model in gk.MODELS:  # LLM quota/overload must never stop a review
        try:
            return asyncio.run(_run(target, True, run_setup, project, quiet, model))
        except Exception as e:
            _log(f"  ! {model} failed ({type(e).__name__}: {str(e)[:120]}); trying next option", quiet)
    rep = asyncio.run(_run(target, False, run_setup, project, quiet))
    rep.notes.append("AI review unavailable; deterministic checks only.")
    return rep


def _post(rep, yes: bool) -> None:
    sub = rep.submission
    m = PR_RX.search(sub.url or "")
    if not m:
        print("--post needs a PR URL target.", file=sys.stderr)
        return
    repo = f"{m.group(1)}/{m.group(2)}"
    if not yes:
        ans = input(f"\nPost this review as a comment on {repo}#{sub.number}? [y/N] ").strip().lower()
        if ans != "y":
            print("Not posted.")
            return
    subprocess.run(["gh", "pr", "comment", str(sub.number), "--repo", repo, "--body-file", "-"],
                   input=rep.review_markdown, text=True, check=True)
    print(f"Posted review to {sub.url}")


def cmd_review(a) -> int:
    rep = review(a.target, use_llm=a.llm, run_setup=a.run_setup, project=a.project, quiet=a.quiet)
    print(rep.review_markdown)
    if a.json:
        Path(a.json).write_text(render.dump(render.to_json(rep)))
        _log(f"JSON written to {a.json}", a.quiet)
    if a.post:
        _post(rep, a.yes)
    return EXIT[rep.verdict]


def cmd_triage(a) -> int:
    prs = github_api(f"repos/{a.repo}/pulls?state=open&per_page={min(a.limit, 100)}")[: a.limit]
    _log(f"Triaging {len(prs)} open PRs in {a.repo}")
    results = []
    for i, pr in enumerate(prs, 1):
        _log(f"[{i}/{len(prs)}] #{pr['number']} {pr['title'][:60]}")
        try:
            rep = review(pr["html_url"], use_llm=a.llm, run_setup=a.run_setup, quiet=True)
            results.append(render.to_json(rep))
        except Exception as e:
            results.append({"url": pr["html_url"], "number": pr["number"], "title": pr["title"],
                            "author": pr["user"]["login"], "project": None, "verdict": "error", "score": 0,
                            "findings": [{"severity": "blocker", "message": f"Could not review: {e}"}]})
    Path(a.out).write_text(render.dashboard(results, a.repo))
    Path(a.out).with_suffix(".json").write_text(render.dump(results))
    _log(f"Board written to {a.out} (+ .json)")
    return 0


def cmd_fix(a) -> int:
    from . import fixer

    rep = review(a.target, use_llm=False, project=a.project, quiet=a.quiet)
    fixes = fixer.plan(rep, use_llm=a.llm)
    print(fixer.render(fixes))
    if a.apply:
        for line in fixer.apply(rep, fixes):
            print(line)
        after = review(a.target, use_llm=False, project=a.project, quiet=True)
        print(f"\nVerdict: {rep.verdict.value} ({rep.score()}/100) -> {after.verdict.value} ({after.score()}/100)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mergewarden", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    llm_default = gk.llm_available()

    r = sp.add_parser("review", help="review one PR (URL) or a local contribution (path)")
    r.add_argument("target", help="https://github.com/OWNER/REPO/pull/N, OWNER/REPO#N, or a local path")
    r.add_argument("--project", help="project folder when reviewing locally, e.g. agents/my-agent")
    r.add_argument("--json", help="also write the machine-readable report here")
    r.add_argument("--run-setup", action="store_true", help="fresh-install test in a Docker sandbox")
    r.add_argument("--post", action="store_true", help="post the review as a PR comment (asks first)")
    r.add_argument("--yes", action="store_true", help="with --post: don't ask for confirmation (CI)")
    r.add_argument("-q", "--quiet", action="store_true")
    r.set_defaults(func=cmd_review)

    t = sp.add_parser("triage", help="review all open PRs and build an HTML triage board")
    t.add_argument("repo", help="OWNER/REPO")
    t.add_argument("--out", default="triage.html")
    t.add_argument("--limit", type=int, default=50)
    t.add_argument("--run-setup", action="store_true")
    t.set_defaults(func=cmd_triage)

    f = sp.add_parser("fix", help="plan (and with --apply, write) fixes for a local contribution")
    f.add_argument("target", help="local path to your contribution folder")
    f.add_argument("--project", help="project folder, e.g. agents/my-agent")
    f.add_argument("--apply", action="store_true", help="write file fixes inside your project folder (never runs commands)")
    f.add_argument("-q", "--quiet", action="store_true")
    f.set_defaults(func=cmd_fix)

    for sub in (r, t, f):
        g = sub.add_mutually_exclusive_group()
        g.add_argument("--llm", dest="llm", action="store_true", default=llm_default,
                       help="use Gemini reviewers (default when an API key is set)")
        g.add_argument("--no-llm", dest="llm", action="store_false", help="deterministic checks only, offline")

    a = p.parse_args(argv)
    return a.func(a)
