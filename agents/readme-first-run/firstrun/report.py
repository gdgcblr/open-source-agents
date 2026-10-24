"""Markdown and JSON reports for a FirstRun check."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from .models import Plan, Report, RunResult, to_dict

VERDICT_LABEL = {
    "passed": "PASSED",
    "fixed": "FIXED (failed as documented, fix verified)",
    "blocked": "BLOCKED (needs something FirstRun cannot provide)",
    "failed": "FAILED (no verified fix)",
    "error": "ERROR (FirstRun could not run)",
}


def _cell(text: str, width: int = 80) -> str:
    one = " ".join(str(text).split()).replace("|", "\\|")
    if len(one) > width:
        one = one[: width - 3] + "..."
    return f"`{one}`" if one else ""


def _tail(text: str, lines: int = 30) -> str:
    rows = text.rstrip().splitlines()
    cut = rows[-lines:]
    prefix = [f"... ({len(rows) - lines} earlier lines in the log)"] if len(rows) > lines else []
    return "\n".join(prefix + cut)


def _log_name(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") + ".log"


def _steps_table(run: RunResult) -> list[str]:
    out = ["| # | Command | README line | Status | Exit | Time |", "|---|---|---|---|---|---|"]
    for r in run.results:
        line = str(r.step.line) if r.step.line else ""
        code = "" if r.exit_code is None else str(r.exit_code)
        status = r.status + (" (provided by FirstRun)" if r.step.provided_by_firstrun else "")
        out.append(f"| {r.step.index} | {_cell(r.step.command)} | {line} | {status} | {code} | {r.duration:.1f}s |")
    return out


def _run_section(run: RunResult) -> list[str]:
    out = [f"Sandbox: {run.sandbox}. Result: **{run.status}** in {run.duration:.1f}s.", ""]
    out += _steps_table(run)
    failed = run.failed_step
    if failed is not None:
        out += ["", f"Output of step {failed.step.index}:", "", "```text", _tail(failed.output) or "(no output)", "```"]
    if run.error:
        out += ["", f"Sandbox error: {run.error}"]
    out += ["", f"Full log: `logs/{_log_name(run.label)}`"]
    return out


def _plan_notes(plan: Plan) -> list[str]:
    out = []
    if plan.skipped:
        out += ["", "README lines FirstRun did not run:", ""]
        for s in plan.skipped:
            where = f" (line {s.line})" if s.line else ""
            out.append(f"- {_cell(s.command, 70)}{where}: {s.reason}")
    for note in plan.notes:
        out.append(f"- Note: {note}")
    return out


def render_markdown(report: Report) -> str:
    s = report.settings
    out = [
        f"# FirstRun report: {report.project}",
        "",
        f"**Verdict: {VERDICT_LABEL.get(report.verdict, report.verdict)}**",
        "",
        report.headline,
        "",
        "| | |",
        "|---|---|",
        f"| Source | {report.source} |",
        f"| Sandbox | {s.get('sandbox_detail', s.get('sandbox', ''))} |",
        f"| Reasoning | {s.get('engine', '')} |",
        f"| Started | {report.started_at} |",
        f"| Duration | {s.get('duration_seconds', '?')}s |",
    ]
    m = report.metrics or {}
    if m.get("time_to_first_success") is not None:
        out.append(f"| Time to first success | {m['time_to_first_success']}s for a fresh install, "
                   f"{m.get('fixes_applied', 0)} fix(es), {m.get('sandbox_runs', 0)} sandbox run(s) |")
    if s.get("env_keys"):
        out.append(f"| Secrets supplied | {', '.join(s['env_keys'])} (values never stored) |")
    if report.error:
        out += ["", f"Error: {report.error}"]

    plan = report.documented_plan
    if plan is not None:
        out += ["", "## 1. Steps a newcomer would run", "",
                f"Read from `{plan.readme_path or 'no README'}` by the {plan.engine} planner: "
                f"{len(plan.steps)} steps."]
        out += _plan_notes(plan)

    if report.documented_run is not None:
        out += ["", "## 2. As documented", ""] + _run_section(report.documented_run)

    for rnd in report.rounds:
        d = rnd.diagnosis
        out += ["", f"## 3.{rnd.number} Diagnosis", "",
                f"**{d.summary}**", "",
                f"Category: `{d.category}`, confidence {d.confidence}, found by {d.engine}."]
        if d.explanation.strip():
            out += ["", d.explanation.strip()]
        if d.evidence:
            out += ["", "Evidence:", ""]
            for ev in d.evidence:
                loc = f"{ev.file}:{ev.line}" if ev.line else ev.file
                out.append(f"- `{loc}`: {ev.note}")
        if d.missing_env:
            out += ["", f"Missing credentials: {', '.join(d.missing_env)}. Supply them with "
                        "`--env-file` or `--pass-env` to continue past this point."]
        if d.trace:
            out += ["", f"<details><summary>Investigator trace ({len(d.trace)} tool calls)</summary>", ""]
            for call in d.trace:
                out.append(f"- `{call.get('tool')}` {json.dumps(call.get('args', {}))}")
            out += ["", "</details>"]
        if rnd.diff:
            out += ["", "Suggested correction:", "", "```diff", rnd.diff.rstrip(), "```"]
        if rnd.verification is not None:
            out += ["", f"### After fix {rnd.number}", ""] + _run_section(rnd.verification)
            if rnd.plan is not None and rnd.plan.skipped != (plan.skipped if plan else []):
                out += _plan_notes(rnd.plan)

    if report.output_check:
        oc = report.output_check
        out += ["", "## Example output check", "",
                f"Compared the README's example output with what `{_cell(oc.get('command', ''), 60).strip('`')}` "
                f"printed: similarity {oc.get('similarity', 0):.2f}, {oc.get('verdict', 'n/a')}."]
        if oc.get("note"):
            out += ["", oc["note"]]

    if report.static_hints:
        out += ["", "## Static hints", ""] + [f"- {h}" for h in report.static_hints]

    if report.final_diff:
        verified = report.verdict == "fixed"
        # paths in the patch are relative to the project folder, and `git apply` run from a
        # subfolder of a bigger repo silently skips them, so plain patch is the safe default
        out += ["", "## Apply the fix", "",
                "The patch was " + ("verified in a fresh sandbox." if verified else "NOT verified, review it carefully."),
                "From inside the project folder:", "", "```bash", "patch -p1 < fix.patch", "```", "",
                "Or from the root of a monorepo: `git apply --directory=<path/to/project> fix.patch`."]
    out.append("")
    return "\n".join(out)


def _json_ready(report: Report) -> dict:
    data = to_dict(report)
    # raw logs go to logs/, keep the json small enough to read
    for run in [data.get("documented_run")] + [r.get("verification") for r in data["rounds"]]:
        if run:
            run.pop("log", None)
    return data


def final_passing_run(report: Report) -> Optional[RunResult]:
    if report.verdict == "passed":
        return report.documented_run
    if report.verdict == "fixed":
        return report.rounds[-1].verification
    return None


def verified_setup_script(report: Report) -> Optional[str]:
    """The exact commands that passed in the fresh sandbox, as a script a newcomer can run."""
    run = final_passing_run(report)
    if run is None:
        return None
    source = "the README after applying fix.patch" if report.verdict == "fixed" else "the README as written"
    lines = [
        "#!/usr/bin/env bash",
        f"# Setup for {report.project}, verified by FirstRun on {report.finished_at[:10]} in a fresh {run.sandbox}.",
        f"# Commands come from {source}, in the order they ran.",
        "set -e",
        "",
    ]
    for r in run.results:
        note = "  # starts a server, stays running" if r.step.long_running else ""
        if r.step.provided_by_firstrun:
            note = "  # prerequisite FirstRun installed"
        lines.append(f"# step {r.step.index}" + (f", README line {r.step.line}" if r.step.line else ""))
        lines.append(r.step.command.rstrip() + note)
    return "\n".join(lines) + "\n"


def write_events(events: list[dict], run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "events.jsonl", "w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, default=str) + "\n")


def write_report(report: Report, run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    logs = run_dir / "logs"
    runs: list[Optional[RunResult]] = [report.documented_run] + [r.verification for r in report.rounds]
    for run in runs:
        if run is not None:
            logs.mkdir(exist_ok=True)
            (logs / _log_name(run.label)).write_text(run.log, encoding="utf-8")
    (run_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    (run_dir / "report.json").write_text(json.dumps(_json_ready(report), indent=2, default=str), encoding="utf-8")
    if report.final_diff:
        (run_dir / "fix.patch").write_text(report.final_diff, encoding="utf-8")
    script = verified_setup_script(report)
    if script:
        (run_dir / "verified-setup.sh").write_text(script, encoding="utf-8")
    from .comment import render_comment

    (run_dir / "comment.md").write_text(render_comment(report), encoding="utf-8")
    return run_dir
