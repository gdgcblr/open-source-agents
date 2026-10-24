"""Real-PR regression eval: re-checks pull requests pinned to exact commits against hand-checked verdicts.

    python -m evals.run_real_prs_eval                  # re-check every PR in evals/real_prs.toml
    python -m evals.run_real_prs_eval --only 13 76     # just these PR numbers
    python -m evals.run_real_prs_eval --capture 80 81  # print TOML entries for new PRs, to review by hand

Needs git and network access to the upstream repository. It only reads: each PR commit is fetched into
refs/prcheck/pr/<n> of the repository this tool lives in, checked out in a temporary worktree, and checked
with prcheck. Contributor code is never executed. Remove the refs afterwards with:

    git for-each-ref --format="delete %(refname)" refs/prcheck | git update-ref --stdin

A pinned commit that can no longer be fetched (e.g. after a force-push) is reported as unavailable, not as
a failure. Entries come from hand review only: --capture output is a starting point, not ground truth.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from prcheck import git
from prcheck.models import Status
from prcheck.runner import run

MANIFEST = Path(__file__).parent / "real_prs.toml"
FLAGGED = {Status.FAIL.value, Status.WARN.value, Status.INFO.value}


@dataclass
class PinnedPR:
    number: int
    sha: str
    folder: str
    expect: dict[str, str]
    ready: bool
    reviewed: str
    why: str


@dataclass
class Outcome:
    pr: PinnedPR
    state: str  # "ok", "mismatch", "unavailable"
    mismatches: list[str] = field(default_factory=list)
    statuses: dict[str, str] = field(default_factory=dict)


def load_manifest(path: Path = MANIFEST) -> tuple[dict, list[PinnedPR]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    prs = [PinnedPR(number=p["number"], sha=p["sha"], folder=p["folder"], expect=dict(p.get("expect", {})),
                    ready=p["ready"], reviewed=p["reviewed"], why=p["why"]) for p in data.get("pr", [])]
    meta = {k: v for k, v in data.items() if k != "pr"}
    return meta, prs


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    # core.longpaths: some PRs contain paths longer than Windows' default limit (e.g. PRs #36, #38).
    return subprocess.run(["git", "-c", "core.longpaths=true", *args], cwd=repo, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)


def _has_commit(repo: Path, sha: str) -> bool:
    return _git(repo, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def ensure_commit(repo: Path, url: str, number: int | None, sha: str) -> bool:
    if _has_commit(repo, sha):
        return True
    if number is not None:
        _git(repo, "fetch", "-q", url, f"+refs/pull/{number}/head:refs/prcheck/pr/{number}")
        if _has_commit(repo, sha):
            return True
    _git(repo, "fetch", "-q", url, sha)  # works while the commit is still reachable on GitHub
    return _has_commit(repo, sha)


def check_commit(repo: Path, sha: str, folder: str, base_sha: str) -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="prcheck-realpr-") as tmp:
        worktree = Path(tmp) / "wt"
        added = _git(repo, "worktree", "add", "-q", "--detach", str(worktree), sha)
        if added.returncode != 0:
            raise RuntimeError(f"worktree add failed: {added.stderr.strip()}")
        try:
            report, _ = run(worktree / folder, base=base_sha)
            return {r.id: r.status.value for r in report.checks}
        finally:
            _git(repo, "worktree", "remove", "--force", str(worktree))


def compare(pr: PinnedPR, statuses: dict[str, str]) -> list[str]:
    problems = []
    for check_id, status in statuses.items():
        expected = pr.expect.get(check_id)
        if status == Status.CRASH.value:
            problems.append(f"{check_id} crashed")
        elif expected is None and status in FLAGGED:
            problems.append(f"{check_id} unexpectedly {status}")
        elif expected is not None and status != expected:
            problems.append(f"{check_id} expected {expected}, got {status}")
    for check_id in pr.expect:
        if check_id not in statuses:
            problems.append(f"{check_id} expected {pr.expect[check_id]} but did not run")
    return problems


def evaluate(repo: Path, meta: dict, prs: list[PinnedPR]) -> list[Outcome]:
    outcomes = []
    if not ensure_commit(repo, meta["repo_url"], None, meta["base_sha"]):
        raise SystemExit(f"Base commit {meta['base_sha']} is not available; check network access.")
    for pr in prs:
        if not ensure_commit(repo, meta["repo_url"], pr.number, pr.sha):
            outcomes.append(Outcome(pr, "unavailable"))
            continue
        statuses = check_commit(repo, pr.sha, pr.folder, meta["base_sha"])
        problems = compare(pr, statuses)
        outcomes.append(Outcome(pr, "mismatch" if problems else "ok", problems, statuses))
    return outcomes


def capture(repo: Path, meta: dict, numbers: list[int]) -> None:
    """Print draft TOML entries for the current head of each PR. Review every one before pasting it in."""
    url = meta["repo_url"]
    ensure_commit(repo, url, None, meta["base_sha"])
    for number in numbers:
        fetched = _git(repo, "fetch", "-q", url, f"+refs/pull/{number}/head:refs/prcheck/pr/{number}")
        if fetched.returncode != 0:
            print(f"# PR #{number}: fetch failed: {fetched.stderr.strip()}")
            continue
        sha = _git(repo, "rev-parse", f"refs/prcheck/pr/{number}").stdout.strip()
        mb = _git(repo, "merge-base", meta["base_sha"], sha).stdout.strip()
        changed = _git(repo, "diff", "--name-only", mb, sha).stdout.split()
        folders = sorted({"/".join(p.split("/")[:2]) for p in changed
                          if p.split("/")[0] in ("agents", "tools") and p.count("/") >= 2})
        for folder in folders:
            statuses = check_commit(repo, sha, folder, meta["base_sha"])
            expect = {k: v for k, v in statuses.items() if v in FLAGGED}
            ready = not any(v == Status.FAIL.value for v in statuses.values())
            inline = ", ".join(f'{k} = "{v}"' for k, v in expect.items())
            print(f'\n[[pr]]  # DRAFT - review by hand, then fill in reviewed/why\nnumber = {number}\n'
                  f'sha = "{sha}"\nfolder = "{folder}"\nexpect = {{ {inline} }}\nready = {str(ready).lower()}\n'
                  f'reviewed = ""\nwhy = ""')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", type=int, nargs="+", help="Only re-check these PR numbers.")
    parser.add_argument("--capture", type=int, nargs="+", help="Print draft entries for these PRs and exit.")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)

    if not git.available():
        print("git is required for this eval.")
        return 2
    repo = git.toplevel(Path(__file__).resolve().parent)
    if repo is None:
        print("Run this from inside a clone of the repository.")
        return 2
    meta, prs = load_manifest()

    if args.capture:
        capture(repo, meta, args.capture)
        return 0

    if args.only:
        prs = [p for p in prs if p.number in set(args.only)]
    outcomes = evaluate(repo, meta, prs)
    print(f"Real-PR regression eval: {meta['repo_url']} (base {meta['base_sha'][:7]}, "
          f"reviewed {meta['reviewed_on']})\n")
    for o in outcomes:
        mark = {"ok": "OK  ", "mismatch": "FAIL", "unavailable": "GONE"}[o.state]
        print(f"  {mark} #{o.pr.number:<4} {o.pr.folder:<44} {o.pr.sha[:7]}  {o.pr.why[:70]}")
        for m in o.mismatches:
            print(f"         - {m}")
    ok = sum(o.state == "ok" for o in outcomes)
    gone = sum(o.state == "unavailable" for o in outcomes)
    checked = len(outcomes) - gone
    verdicts = sum(o.state == "ok" or (o.state == "mismatch" and o.pr.ready ==
                                         (not any(v == "fail" for v in o.statuses.values())))
                   for o in outcomes if o.state != "unavailable")
    print(f"\n  {ok}/{checked} PRs match exactly; {verdicts}/{checked} have the right READY / NOT READY verdict; "
          f"{gone} unavailable")
    if args.json:
        args.json.write_text(json.dumps([{"number": o.pr.number, "folder": o.pr.folder, "sha": o.pr.sha,
                                          "state": o.state, "mismatches": o.mismatches, "statuses": o.statuses}
                                         for o in outcomes], indent=2), encoding="utf-8")
    return 0 if ok == checked else 1


if __name__ == "__main__":
    os.environ.setdefault("GIT_CONFIG_COUNT", "1")  # long paths for prcheck's own git calls too
    os.environ.setdefault("GIT_CONFIG_KEY_0", "core.longpaths")
    os.environ.setdefault("GIT_CONFIG_VALUE_0", "true")
    sys.exit(main())
