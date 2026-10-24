"""Command-line interface.

judge run                                # judge every PR of gdgcblr/open-source-agents
judge run --pr 4 --pr 7 --llm off        # selected PRs, static analysis only
judge run --local ../some-agent          # judge a folder on disk (e.g. before opening a PR)
judge show 4                             # print one result in the terminal
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from judge import JUDGE_VERSION, __version__
from judge.llm.client import ChatClient, LLMError
from judge.pipeline import evaluate_all, publish
from judge.scoring import RUBRIC
from judge.sources import GitHubRepoSource, SourceError, local_workspace
from judge.store import from_env

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPO = "gdgcblr/open-source-agents"
VERDICT_ICON = {"ready": "✅ ready", "needs_changes": "🟡 needs changes", "blocked": "⛔ blocked"}


def _client(mode: str) -> tuple[str, ChatClient | None]:
    if mode in ("off", "mock"):
        return mode, None
    try:
        client = ChatClient.from_env()
    except LLMError as exc:
        if mode == "on":
            raise SystemExit(f"--llm on but no provider is configured: {exc}") from exc
        logging.getLogger(__name__).info("no LLM provider configured; running static analysis only")
        return "off", None
    return "on", client


def cmd_run(args: argparse.Namespace) -> int:
    cache = Path(args.cache_dir)
    store = from_env(args.store, cache / "records", Path(args.out))
    llm_mode, client = _client(args.llm)
    progress = print if not args.quiet else (lambda _: None)
    progress(
        f"AI Repo Judge {__version__} (rules {JUDGE_VERSION}) · store={store.name} · llm={llm_mode}"
        + (f" ({', '.join(client.available)})" if client else "")
    )

    if args.local:
        workspaces = {}
        metas = []
        for folder in args.local:
            ws = local_workspace(Path(folder))
            workspaces[ws.meta.id] = ws
            metas.append(ws.meta)
        records = evaluate_all(
            lambda m: workspaces[m.id],
            store,
            metas,
            llm_mode=llm_mode,
            client=client,
            refresh=True,
            online=not args.offline,
            progress=progress,
        )
        repo = None
    else:
        source = GitHubRepoSource(args.repo, cache, token=os.getenv("GITHUB_TOKEN"))
        try:
            source.sync()
        except (SourceError, OSError) as exc:
            raise SystemExit(f"could not sync {args.repo}: {exc}") from exc
        metas = source.list_prs(args.state)
        if args.pr:
            wanted = {str(n) for n in args.pr}
            metas = [m for m in metas if m.id in wanted]
        if args.limit:
            metas = metas[: args.limit]
        progress(f"{len(metas)} pull request(s) from {args.repo}")
        records = evaluate_all(
            source,
            store,
            metas,
            llm_mode=llm_mode,
            client=client,
            refresh=args.refresh,
            online=not args.offline,
            progress=progress,
        )
        repo = args.repo

    index, details = publish(store, records, repo)
    where = store.publish(index, details)
    progress(f"\nPublished {len(details)} submission(s) → {where}")
    for row in index["submissions"]:
        progress(
            f"  {('#' + str(row['number'])) if row['number'] else row['id']:>10}  {row['overall']:>3}/100  "
            f"{VERDICT_ICON[row['verdict']]:<17} {row['slug']}"
        )
    for err in index["errors"]:
        progress(f"  #{err['id']:>9}  skipped: {err['error']}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    path = Path(args.out) / "pr" / f"{args.id}.json"
    if not path.exists():
        raise SystemExit(f"{path} not found; run `judge run` first")
    s = json.loads(path.read_text(encoding="utf-8"))
    print(f"{s['title']}  ({s['project_path']})\n{s['url'] or ''}")
    print(
        f"Overall {s['overall']}/100 · {VERDICT_ICON[s['verdict']]} · confidence {s['confidence']}% · "
        f"AI level {s['ai_level']} ({s['ai_level_label']})"
    )
    for gate in s["gates"]:
        print(f"  ⛔ {gate}")
    for d in s["dimensions"]:
        score = "n/a" if d["score"] is None else f"{d['score']:>3}"
        print(f"\n{d['label']:<34} {score}   (weight {d['weight']:.0%})")
        for c in d["checks"]:
            mark = {"pass": "✓", "warn": "!", "fail": "✗", "skip": "-"}[c["status"]]
            print(f"   {mark} {c['label']}: {c['detail']}")
    if s["top_fixes"]:
        print("\nTop fixes:")
        for i, fix in enumerate(s["top_fixes"], 1):
            print(f"  {i}. {fix}")
    return 0


def cmd_rubric(_: argparse.Namespace) -> int:
    for d in RUBRIC:
        print(f"{d.label:<34} {d.weight:>4.0%}  LLM≤{d.llm_share:.0%}  {d.purpose}")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    p = argparse.ArgumentParser(prog="judge", description="Evidence-based AI judge for agent/tool submissions.")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="judge pull requests or local folders and publish dashboard data")
    run.add_argument("--repo", default=os.getenv("JUDGE_REPO", DEFAULT_REPO), help="GitHub owner/name")
    run.add_argument("--pr", type=int, action="append", help="only these PR numbers (repeatable)")
    run.add_argument("--state", choices=("open", "closed", "all"), default="all")
    run.add_argument("--local", action="append", help="judge a local folder instead of PRs (repeatable)")
    run.add_argument(
        "--llm",
        choices=("auto", "on", "off", "mock"),
        default=os.getenv("JUDGE_LLM", "auto"),
        help="auto = use an LLM if a provider key is configured",
    )
    run.add_argument("--refresh", action="store_true", help="re-evaluate even if the head commit is unchanged")
    run.add_argument("--offline", action="store_true", help="skip network lookups (OSV vulnerability check)")
    run.add_argument("--limit", type=int, help="judge at most N PRs")
    run.add_argument("--store", choices=("local", "firestore"), help="default: $JUDGE_STORE or local")
    run.add_argument("--out", default=os.getenv("JUDGE_OUT", str(ROOT / "data")), help="dashboard data directory")
    run.add_argument("--cache-dir", default=os.getenv("JUDGE_CACHE", str(ROOT / ".cache")))
    run.add_argument("-q", "--quiet", action="store_true")
    run.set_defaults(func=cmd_run)

    show = sub.add_parser("show", help="print one judged submission")
    show.add_argument("id")
    show.add_argument("--out", default=os.getenv("JUDGE_OUT", str(ROOT / "data")))
    show.set_defaults(func=cmd_show)

    sub.add_parser("rubric", help="print the scoring rubric").set_defaults(func=cmd_rubric)

    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
