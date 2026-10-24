"""Batch mode: check every project in a monorepo (or every open PR) and print a scoreboard.

    python -m firstrun.scan --prs gdgcblr/open-source-agents --list
    python -m firstrun.scan --root ../.. --dirs agents,tools --offline

Only read-only gh calls are made. Nothing is ever posted to GitHub.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import agent
from .agent import Settings
from .models import Report

SELF_SLUG = "readme-first-run"
DEFAULT_DIRS = ("agents", "tools")
VERDICT_WORD = {
    "passed": "PASSED", "fixed": "FIXED", "blocked": "BLOCKED", "failed": "FAILED",
    "error": "ERROR", "skipped": "SKIPPED",
}
PR_FIELDS = "number,title,author,headRefName,headRepository,headRepositoryOwner,files,url"


class ScanError(RuntimeError):
    pass


@dataclass
class Target:
    label: str  # "PR #12 agents/foo" or "agents/foo"
    folder: str  # agents/foo, or "" when a PR touches no project folder
    target: str  # GitHub tree URL or local path, "" when skipped
    author: str = ""
    pr: Optional[int] = None
    pr_url: str = ""
    title: str = ""
    skip: str = ""  # reason this one is not checked


@dataclass
class Row:
    label: str
    folder: str
    author: str
    pr: Optional[int]
    pr_url: str
    verdict: str
    failed_at: str = ""
    summary: str = ""
    time_to_first_success: Optional[float] = None
    run_dir: str = ""
    headline: str = ""


def project_folders(paths: list[str], dirs: tuple[str, ...] = DEFAULT_DIRS) -> list[str]:
    """agents/<slug> and tools/<slug> folders touched by a list of file paths, in first-seen order."""
    pattern = re.compile(r"^(%s)/([^/]+)/" % "|".join(re.escape(d) for d in dirs))
    found: list[str] = []
    for path in paths:
        m = pattern.match(path)
        if m:
            folder = f"{m.group(1)}/{m.group(2)}"
            if folder not in found:
                found.append(folder)
    return found


def tree_url(owner: str, repo: str, ref: str, folder: str) -> str:
    return f"https://github.com/{owner}/{repo}/tree/{ref}/{folder}"


def _run_gh(args: list[str]) -> subprocess.CompletedProcess:
    if shutil.which("gh") is None:
        raise ScanError("the GitHub CLI (gh) is not installed. Get it from https://cli.github.com and run `gh auth login`")
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise ScanError("gh did not answer within 2 minutes") from exc


def _login(user: Optional[dict]) -> str:
    return (user or {}).get("login") or ""


def discover_prs(repo: str, dirs: tuple[str, ...] = DEFAULT_DIRS) -> list[Target]:
    result = _run_gh(["pr", "list", "--repo", repo, "--state", "open", "--json", PR_FIELDS, "--limit", "100"])
    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip()
        if re.search(r"auth login|not logged|authentication", err, re.IGNORECASE):
            raise ScanError("gh is not logged in. Run `gh auth login` and try again")
        raise ScanError(f"gh pr list failed: {err[-300:]}")
    try:
        prs = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise ScanError(f"could not read gh output: {exc}") from exc

    targets: list[Target] = []
    for pr in sorted(prs, key=lambda p: p.get("number", 0)):
        number, author = pr.get("number"), _login(pr.get("author"))
        base = dict(author=author, pr=number, pr_url=pr.get("url", ""), title=pr.get("title", ""))
        folders = project_folders([f.get("path", "") for f in pr.get("files") or []], dirs)
        if not folders:
            targets.append(Target(label=f"PR #{number}", folder="", target="",
                                  skip=f"touches no {' or '.join(d + '/' for d in dirs)} project folder", **base))
            continue
        head_repo = pr.get("headRepository") or {}
        owner = _login(pr.get("headRepositoryOwner"))
        ref = pr.get("headRefName") or ""
        for folder in folders:
            label = f"PR #{number} {folder}"
            if folder.split("/", 1)[1] == SELF_SLUG:
                targets.append(Target(label, folder, "", skip="FirstRun itself, dogfooded separately", **base))
            elif not head_repo.get("name") or not owner or not ref:
                targets.append(Target(label, folder, "", skip="the head repository was deleted", **base))
            else:
                targets.append(Target(label, folder, tree_url(owner, head_repo["name"], ref, folder), **base))
    return targets


def discover_local(root: Path, dirs: tuple[str, ...] = DEFAULT_DIRS) -> list[Target]:
    if not root.is_dir():
        raise ScanError(f"{root} is not a folder")
    targets: list[Target] = []
    for d in dirs:
        base = root / d
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir() or child.name.startswith((".", "_")):
                continue
            folder = f"{d}/{child.name}"
            if child.name == SELF_SLUG:
                targets.append(Target(folder, folder, "", skip="FirstRun itself, dogfooded separately"))
            else:
                targets.append(Target(folder, folder, str(child.resolve())))
    return targets


def select(targets: list[Target], only: list[str], limit: Optional[int]) -> list[Target]:
    """Apply --only and --limit to the checkable targets. Skipped ones are kept for the record."""
    picked, count = [], 0
    for t in targets:
        if t.skip:
            picked.append(t)
            continue
        slug = t.folder.split("/", 1)[-1]
        if only and slug not in only and t.folder not in only:
            continue
        if limit is not None and count >= limit:
            continue
        picked.append(t)
        count += 1
    return picked


def _cell(text: str, width: int = 90) -> str:
    one = " ".join(str(text or "").split()).replace("|", "\\|")
    return one if len(one) <= width else one[: width - 3] + "..."


def _row_from_report(t: Target, report: Report, run_dir: Path, scan_dir: Path) -> Row:
    failed_at = ""
    failed = report.documented_run.failed_step if report.documented_run else None
    if failed is not None:
        failed_at = f"{failed.step.index}: {failed.step.command}"
    if report.rounds:
        summary = report.rounds[-1].diagnosis.summary
    elif report.verdict == "error":
        summary = report.error or report.headline
    else:
        summary = ""
    try:
        rel = run_dir.relative_to(scan_dir)
    except ValueError:
        rel = run_dir
    return Row(
        label=t.label, folder=t.folder, author=t.author, pr=t.pr, pr_url=t.pr_url,
        verdict=report.verdict, failed_at=failed_at, summary=summary,
        time_to_first_success=(report.metrics or {}).get("time_to_first_success"),
        run_dir=str(rel), headline=report.headline,
    )


def render_scoreboard(rows: list[Row], skipped: list[Target], *, source: str, started: str,
                      sandbox: str, engine: str) -> str:
    counts = {v: sum(1 for r in rows if r.verdict == v) for v in ("passed", "fixed", "blocked", "failed", "error")}
    out = [
        f"# FirstRun scoreboard: {source}",
        "",
        f"Checked {len(rows)} project{'s' if len(rows) != 1 else ''} on {started} in {sandbox}, "
        f"reasoning by {engine}. Each README was followed from scratch in a fresh sandbox.",
        "",
        f"**{counts['passed']} work as documented, {counts['fixed']} fixed by a verified patch, "
        f"{counts['blocked']} blocked on credentials, {counts['failed']} failed, {counts['error']} could not be checked.**",
    ]
    if rows:
        out += [
            "",
            "| PR / folder | Author | Verdict | Failed at step | Diagnosis | Time to first success | Report |",
            "| :--- | :--- | :--- | :--- | :--- | ---: | :--- |",
        ]
        for r in rows:
            where = f"[#{r.pr}]({r.pr_url}) `{r.folder}`" if r.pr and r.pr_url else f"`{r.folder or r.label}`"
            author = f"@{r.author}" if r.author else ""
            failed = f"`{_cell(r.failed_at, 50)}`" if r.failed_at else ""
            ttfs = f"{r.time_to_first_success:.0f}s" if r.time_to_first_success is not None else ""
            link = f"[report]({r.run_dir}/report.md)" if r.run_dir else ""
            out.append(f"| {where} | {author} | {VERDICT_WORD.get(r.verdict, r.verdict.upper())} | {failed} "
                       f"| {_cell(r.summary)} | {ttfs} | {link} |")
    if skipped:
        out += ["", "Not checked:", ""]
        for t in skipped:
            name = f"[#{t.pr}]({t.pr_url})" if t.pr and t.pr_url else t.label
            title = f" {_cell(t.title, 60)}" if t.title else ""
            folder = f" `{t.folder}`" if t.folder else ""
            out.append(f"- {name}{title}{folder}: {t.skip}")
    out += ["", "Generated by FirstRun. Verdicts: PASSED works as written, FIXED failed as written but a "
                "suggested patch passed from scratch, BLOCKED needs an API key, FAILED no verified fix.", ""]
    return "\n".join(out)


def run_scan(targets: list[Target], settings: Settings, *, source: str, out: Path,
             stream=sys.stdout) -> tuple[Path, list[Row]]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    scan_dir = Path(out) / f"scan-{stamp}"
    (scan_dir / "runs").mkdir(parents=True, exist_ok=True)
    runnable = [t for t in targets if not t.skip]
    skipped = [t for t in targets if t.skip]
    rows: list[Row] = []
    engine, sandbox = "", settings.sandbox
    started = datetime.now().strftime("%Y-%m-%d %H:%M")

    for i, t in enumerate(runnable, 1):
        print(f"[{i}/{len(runnable)}] {t.label} ...", end=" ", file=stream, flush=True)
        t0 = time.time()
        slug = re.sub(r"[^a-z0-9]+", "-", t.folder.lower()).strip("-") or "project"
        run_dir = scan_dir / "runs" / f"{i:02d}-{slug}"
        try:
            report, run_dir = agent.run_check(t.target, settings, run_dir=run_dir)
            row = _row_from_report(t, report, run_dir, scan_dir)
            engine = engine or report.settings.get("engine", "")
            sandbox = report.settings.get("sandbox_detail", sandbox)
        except Exception as exc:  # one broken project must not stop the scan
            row = Row(label=t.label, folder=t.folder, author=t.author, pr=t.pr, pr_url=t.pr_url,
                      verdict="error", summary=f"FirstRun crashed: {exc}")
        rows.append(row)
        extra = f", failed at step {row.failed_at.split(':', 1)[0]}" if row.failed_at else ""
        print(f"{VERDICT_WORD.get(row.verdict, row.verdict.upper())} in {time.time() - t0:.0f}s{extra}",
              file=stream, flush=True)

    md = render_scoreboard(rows, skipped, source=source, started=started, sandbox=sandbox,
                           engine=engine or ("rules (offline)" if settings.offline else "gemini or rules"))
    (scan_dir / "scoreboard.md").write_text(md, encoding="utf-8")
    data = {
        "source": source, "started": started, "settings": settings.public(),
        "counts": {v: sum(1 for r in rows if r.verdict == v) for v in VERDICT_WORD if v != "skipped"},
        "rows": [asdict(r) for r in rows],
        "skipped": [asdict(t) for t in skipped],
    }
    (scan_dir / "scoreboard.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return scan_dir, rows


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m firstrun.scan",
        description="Check every project in a monorepo, or every open PR, and write a scoreboard.",
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--prs", metavar="OWNER/REPO", help="check the project folders changed by each open PR")
    src.add_argument("--root", type=Path, help="check every project folder in a local checkout")
    p.add_argument("--dirs", default="agents,tools", help="comma separated folders that hold projects")
    p.add_argument("--list", action="store_true", help="only print what would be checked")
    p.add_argument("--only", action="append", default=[], metavar="SLUG", help="check only this project (repeatable)")
    p.add_argument("--limit", type=int, help="check at most N projects")
    p.add_argument("--sandbox", choices=("docker", "local"), default="docker")
    p.add_argument("--image", default="python:3.12-slim")
    p.add_argument("--offline", action="store_true", help="skip Gemini and use the built-in rules only")
    p.add_argument("--max-rounds", type=int, default=2)
    p.add_argument("--no-repair", action="store_true")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--watch", type=int, default=20)
    p.add_argument("--out", type=Path, default=Path("runs"))
    return p


def main(argv: Optional[list[str]] = None, stream=sys.stdout) -> int:
    args = build_parser().parse_args(argv)
    dirs = tuple(d.strip().strip("/") for d in args.dirs.split(",") if d.strip())
    try:
        if args.prs:
            source = f"{args.prs} open PRs"
            targets = discover_prs(args.prs, dirs)
        else:
            source = str(args.root)
            targets = discover_local(args.root, dirs)
    except ScanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    targets = select(targets, args.only, args.limit)
    runnable = [t for t in targets if not t.skip]

    if args.list:
        for t in targets:
            if t.skip:
                print(f"skip   {t.label}: {t.skip}", file=stream)
            else:
                who = f" by @{t.author}" if t.author else ""
                print(f"check  {t.label}{who}  {t.target}", file=stream)
        print(f"{len(runnable)} to check, {len(targets) - len(runnable)} skipped", file=stream)
        return 0
    if not runnable:
        print("nothing to check", file=stream)
        return 0

    from .cli import load_own_dotenv

    load_own_dotenv()
    settings = Settings(
        sandbox=args.sandbox, image=args.image, offline=args.offline, max_rounds=args.max_rounds,
        repair=not args.no_repair, timeout=args.timeout, watch_seconds=args.watch, out_dir=args.out,
    )
    scan_dir, _ = run_scan(targets, settings, source=source, out=args.out, stream=stream)
    print(f"\nScoreboard: {scan_dir / 'scoreboard.md'}", file=stream)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
