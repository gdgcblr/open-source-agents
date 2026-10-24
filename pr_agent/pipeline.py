"""Deterministic orchestration: polling, dedup, approval checks, workspaces, retry limits, audit log."""
from __future__ import annotations

import asyncio
import json
import re
import threading
import time
import traceback

from .config import Config, RepoConfig
from .db import DB
from .github import GitHub
from .policy import PolicyError, run_command
from . import workspace as ws

# Deterministic red flags, independent of the model's opinion.
RED_FLAGS = [
    (r"^\+.*\b(eval|exec)\s*\(", "Adds dynamic code execution (eval/exec)."),
    (r"^\+.*(os\.system|subprocess\.|child_process|Runtime\.getRuntime)", "Adds process execution."),
    (r"^\+.*(curl|wget)[^\n]*\|\s*(ba)?sh", "Pipes a download into a shell."),
    (r"^\+.*(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|-----BEGIN [A-Z ]*PRIVATE KEY)", "Diff contains what looks like a secret."),
    (r"^\+\+\+ b/\.github/workflows/", "Changes CI workflows."),
    (r"^\+\+\+ b/(setup\.py|package\.json|requirements[^/]*\.txt|pyproject\.toml)", "Changes dependencies or install scripts."),
    (r"^\+.*\bpickle\.loads?\(", "Adds unpickling (possible unsafe deserialization)."),
]


def prescan(diff: str) -> list[str]:
    return [msg for pat, msg in RED_FLAGS if re.search(pat, diff, re.MULTILINE)]


class Engine:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.db = DB(cfg.db_path)
        self.gh = GitHub(cfg.github_token)
        self.repos = {r.name: r for r in cfg.repos}
        self._stop = threading.Event()
        self._wake = threading.Event()

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        n = self.db.recover()
        if n:
            print(f"Recovered {n} interrupted run(s).")
        for r in self.cfg.repos:
            self.db.upsert_repo(r.name, "starting")
        threading.Thread(target=self._monitor_loop, name="monitor", daemon=True).start()
        threading.Thread(target=self._worker_loop, name="worker", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def poll_now(self) -> None:
        self._wake.set()

    # ------------------------------------------------------------ monitoring
    def _monitor_loop(self) -> None:
        while not self._stop.is_set():
            for repo in self.cfg.repos:
                try:
                    self.poll_repo(repo)
                    self.db.upsert_repo(repo.name, "monitoring")
                except Exception as e:
                    self.db.upsert_repo(repo.name, "error", str(e)[:500])
                    self.db.log(f"Polling {repo.name} failed: {e}", level="error")
            self._wake.wait(self.cfg.poll_interval_seconds)
            self._wake.clear()

    def _filtered(self, pr: dict) -> str | None:
        if self.cfg.skip_drafts and pr.get("draft"):
            return "draft"
        if pr["user"]["login"] in self.cfg.exclude_authors:
            return "excluded author"
        labels = {l["name"] for l in pr.get("labels", [])}
        if labels & set(self.cfg.exclude_labels):
            return "excluded label"
        return None

    def poll_repo(self, repo: RepoConfig) -> None:
        open_numbers = set()
        for pr in self.gh.open_pulls(repo.name):
            open_numbers.add(pr["number"])
            pr_id, changed = self.db.upsert_pr(repo.name, pr)
            row = self.db.get_pr(pr_id)
            reason = self._filtered(pr)
            if reason:
                if row["status"] != "filtered":
                    self.db.set_pr(pr_id, status="filtered")
                continue
            sha = pr["head"]["sha"]
            prior = self.db.one("SELECT status FROM runs WHERE pr_id=? AND kind='evaluate' AND sha=? "
                                "ORDER BY id DESC LIMIT 1", (pr_id, sha))
            if prior and prior["status"] != "interrupted":
                continue  # this revision was already handled; re-evaluation is a manual action
            if changed and row["status"] in ("approved", "done", "failed", "evaluated", "rejected"):
                self.db.log(f"New commits ({sha[:7]}); previous evaluation and approval no longer apply.", pr_id)
            if self.db.enqueue(pr_id, "evaluate", sha):
                self.db.set_pr(pr_id, status="queued")
                self.db.log(f"Queued evaluation of {sha[:7]}.", pr_id)
        # PRs closed upstream
        for row in self.db.q("SELECT id, number, status FROM prs WHERE repo=? AND state='open'", (repo.name,)):
            if row["number"] not in open_numbers:
                self.db.set_pr(row["id"], state="closed")

    # ------------------------------------------------------------ worker
    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            run = self.db.next_run()
            if not run:
                time.sleep(2)
                continue
            pr = self.db.get_pr(run["pr_id"])
            log = lambda m, lvl="info": self.db.log(m, run["pr_id"], run["id"], lvl)  # noqa: E731
            try:
                if run["kind"] == "evaluate":
                    self.evaluate(run, pr, log)
                else:
                    self.implement(run, pr, log)
            except Exception as e:
                log(f"Run failed: {e}", "error")
                self.db.finish_run(run["id"], "failed", error=f"{e}\n{traceback.format_exc()[-2000:]}")
                self.db.set_pr(pr["id"], status="error" if run["kind"] == "evaluate" else "failed")

    # ------------------------------------------------------------ evaluation
    def evaluate(self, run: dict, pr: dict, log) -> None:
        from .agents import evaluator_agent, parse_json, run_agent
        repo = pr["repo"]
        self.db.set_pr(pr["id"], status="evaluating")
        log("Fetching diff and changed files.")
        files = self.gh.pull_files(repo, pr["number"])
        diff = self.gh.pull_diff(repo, pr["number"])
        flags = prescan(diff)
        file_list = "\n".join(f"{f['status']} {f['filename']} (+{f['additions']}/-{f['deletions']})" for f in files)
        truncated = diff[: self.cfg.max_diff_chars]
        prompt = f"""Evaluate this pull request.
<untrusted>
Repository: {repo}
PR #{pr['number']}: {pr['title']}
Author: {pr['author']}
Description:
{(pr.get('body') or '(none)')[:3000]}

Changed files:
{file_list}

Diff{' (truncated)' if len(diff) > len(truncated) else ''}:
{truncated}
</untrusted>
Automated scanner flags: {flags or 'none'}"""
        log(f"Asking the PR Evaluator ({self.cfg.model}).")
        text = asyncio.run(run_agent(evaluator_agent(self.cfg), prompt, 3))
        try:
            ev = parse_json(text)
        except ValueError:
            log("Evaluator reply was not valid JSON; retrying once.", "warn")
            text = asyncio.run(run_agent(evaluator_agent(self.cfg), prompt + "\nReply with JSON only.", 3))
            ev = parse_json(text)
        ev = normalize_evaluation(ev, flags)
        ev["scanner_flags"] = flags
        ev["files"] = [f["filename"] for f in files]
        self.db.set_pr(pr["id"], status="evaluated", evaluated_sha=run["sha"], category=ev["category"],
                       recommendation=ev["recommendation"], risk=ev["risk"], value_score=ev["value_score"],
                       quality_score=ev["quality_score"], evaluation_json=json.dumps(ev), approved_sha=None)
        self.db.finish_run(run["id"], "succeeded", report=ev)
        log(f"Evaluated: {ev['category']}, value {ev['value_score']}/10, quality {ev['quality_score']}/10, "
            f"risk {ev['risk']}, recommends {ev['recommendation']}.")

    # ------------------------------------------------------------ approval
    def approve(self, pr_id: int) -> str:
        pr = self.db.get_pr(pr_id)
        if not pr or pr["status"] not in ("evaluated", "failed", "interrupted", "stale"):
            raise ValueError("Only evaluated PRs can be approved.")
        if pr["evaluated_sha"] != pr["head_sha"]:
            raise ValueError("The PR changed since it was evaluated. Re-evaluate first.")
        self.db.set_pr(pr_id, status="approved", approved_sha=pr["evaluated_sha"])
        self.db.enqueue(pr_id, "implement", pr["evaluated_sha"])
        self.db.log(f"Implementation approved by user for {pr['evaluated_sha'][:7]}.", pr_id)
        return "approved"

    def reject(self, pr_id: int) -> str:
        self.db.set_pr(pr_id, status="rejected", approved_sha=None)
        self.db.exec("UPDATE runs SET status='stopped', finished_at=datetime('now') WHERE pr_id=? AND status='queued'",
                     (pr_id,))
        self.db.log("Rejected by user.", pr_id)
        return "rejected"

    def reevaluate(self, pr_id: int) -> str:
        pr = self.db.get_pr(pr_id)
        if self.db.enqueue(pr_id, "evaluate", pr["head_sha"]):
            self.db.set_pr(pr_id, status="queued")
            self.db.log("Re-evaluation requested by user.", pr_id)
        return "queued"

    # ------------------------------------------------------------ implementation
    def implement(self, run: dict, pr: dict, log) -> None:
        from .agents import WorkspaceTools, implementation_agent, planning_agent, run_agent, verification_agent
        cfg = self.cfg
        if pr["status"] != "approved" or pr["approved_sha"] != run["sha"]:
            raise PolicyError("No valid user approval for this revision; refusing to implement.")
        log("Re-checking PR revision on GitHub.")
        live = self.gh.pull(pr["repo"], pr["number"])
        if live["head"]["sha"] != run["sha"] or live["state"] != "open":
            self.db.set_pr(pr["id"], status="stale")
            self.db.finish_run(run["id"], "stopped", error="PR changed or closed after approval.")
            log("PR changed or closed after approval. Stopped; re-evaluate before implementing.", "warn")
            return
        self.db.set_pr(pr["id"], status="implementing")
        repo = self.repos.get(pr["repo"]) or RepoConfig(name=pr["repo"])
        log("Creating isolated git worktree.")
        wt, base_commit = ws.create_worktree(cfg, repo, pr["number"], run["sha"], pr["base_ref"])
        self.db.exec("UPDATE runs SET workspace=? WHERE id=?", (str(wt), run["id"]))
        patch = ws.pr_patch(cfg, repo, pr["number"], base_commit)
        checks = repo.checks or ws.detect_checks(wt)
        tools = WorkspaceTools(cfg, wt, patch, checks, lambda m: log(m)).build()
        ev = pr.get("evaluation") or {}
        context = f"""<untrusted>
PR #{pr['number']}: {pr['title']}
Description: {(pr.get('body') or '')[:2000]}
Evaluation summary: {ev.get('summary', '')}
Quality concerns: {ev.get('quality_findings', [])}
Changed files: {ev.get('files', [])}
Diff:
{patch[: cfg.max_diff_chars]}
</untrusted>
Validation commands available: {checks or 'none detected'}"""

        log("Planning Agent is writing the plan.")
        plan = asyncio.run(run_agent(planning_agent(cfg), context, 3))
        log("Plan:\n" + plan[:3000])

        log("Implementation Agent is applying the change.")
        impl = asyncio.run(run_agent(implementation_agent(cfg, tools),
                                     f"{context}\n\nPlan:\n{plan}\n\nImplement it now.",
                                     cfg.max_llm_calls, lambda m: log(m)))
        log("Implementer summary: " + impl[:2000])

        results, attempts = self._validate(wt, checks, log), 0
        while any(r["exit_code"] != 0 for r in results) and attempts < cfg.max_repair_attempts:
            attempts += 1
            failing = "\n\n".join(f"$ {r['command']}\nexit_code={r['exit_code']}\n{r['output'][-3000:]}"
                                  for r in results if r["exit_code"] != 0)
            log(f"Checks failed. Repair attempt {attempts}/{cfg.max_repair_attempts} by the Verification Agent.", "warn")
            diag = asyncio.run(run_agent(verification_agent(cfg, tools),
                                         f"{context}\n\nFailing checks:\n<untrusted>\n{failing}\n</untrusted>",
                                         cfg.max_llm_calls, lambda m: log(m)))
            log("Verifier: " + diag[:2000])
            results = self._validate(wt, checks, log)

        files = ws.changed_files(wt)
        passed = bool(results) and all(r["exit_code"] == 0 for r in results)
        if not files:
            outcome, status = "no_changes", "failed"
        elif not results:
            outcome, status = "unverified", "done"
        else:
            outcome, status = ("passed", "done") if passed else ("checks_failing", "failed")
        report = {
            "outcome": outcome, "workspace": str(wt), "base_commit": base_commit, "plan": plan,
            "implementer_summary": impl, "changed_files": files, "checks": results,
            "repair_attempts": attempts, "diff": ws.diff_text(wt),
            "remaining_issues": [f"`{r['command']}` exits {r['exit_code']}" for r in results if r["exit_code"] != 0]
            + (["No validation commands were found; the change is unverified."] if not results else [])
            + (["The agent made no changes."] if not files else []),
            "note": "Changes are local and uncommitted. Nothing was pushed, merged or published.",
        }
        self.db.finish_run(run["id"], "succeeded" if status == "done" else "failed", report=report)
        self.db.set_pr(pr["id"], status=status)
        log(f"Finished: {outcome}. {len(files)} file(s) changed in {wt}.", "info" if status == "done" else "warn")

    def _validate(self, wt, checks: list[str], log) -> list[dict]:
        results = []
        for c in checks:
            try:
                r = run_command(c, wt, self.cfg.command_timeout_seconds, self.cfg.allowed_commands,
                                self.cfg.python_executable)
            except PolicyError as e:
                r = {"command": c, "exit_code": -1, "output": f"Blocked by execution policy: {e}"}
            log(f"Check `{c}` -> exit {r['exit_code']}", "info" if r["exit_code"] == 0 else "warn")
            results.append(r)
        return results


def normalize_evaluation(ev: dict, flags: list[str]) -> dict:
    def score(v) -> float:
        try:
            return max(0.0, min(10.0, float(v)))
        except (TypeError, ValueError):
            return 0.0

    def lst(v) -> list[str]:
        return [str(x) for x in v] if isinstance(v, list) else ([str(v)] if v else [])

    out = {
        "category": str(ev.get("category", "other")).lower(),
        "value_score": score(ev.get("value_score")),
        "quality_score": score(ev.get("quality_score")),
        "risk": str(ev.get("risk", "medium")).lower(),
        "recommendation": str(ev.get("recommendation", "needs_review")).lower(),
        "summary": str(ev.get("summary", "")),
        "value_findings": lst(ev.get("value_findings")),
        "quality_findings": lst(ev.get("quality_findings")),
        "security_findings": lst(ev.get("security_findings")) + flags,
        "risks": lst(ev.get("risks")),
    }
    if out["risk"] not in ("low", "medium", "high"):
        out["risk"] = "medium"
    if out["recommendation"] not in ("implement", "needs_review", "skip"):
        out["recommendation"] = "needs_review"
    # Scanner flags can only raise risk, never lower it.
    if flags and out["risk"] == "low":
        out["risk"] = "medium"
    if flags and out["recommendation"] == "implement" and out["risk"] == "high":
        out["recommendation"] = "needs_review"
    return out
