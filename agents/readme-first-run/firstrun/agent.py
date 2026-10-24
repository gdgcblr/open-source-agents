"""The FirstRun pipeline: understand, attempt, investigate, repair, verify, report."""

from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import rules
from .llm import LLM, get_llm
from .models import Diagnosis, EventFn, Plan, Report, Round, RunResult, Skipped, noop_event, to_dict
from .project import find_readme, read_text
from .readme import apply_directives, documented_output, extract_plan
from .repair import EditError, apply_edits, copy_project, unified_diff
from .report import write_events, write_report
from .sandbox import DEFAULT_IMAGE, make_sandbox, node_prerequisite, pick_image
from .source import SourceError, resolve_target


@dataclass
class Settings:
    sandbox: str = "docker"  # docker | local
    image: str = DEFAULT_IMAGE
    offline: bool = False
    max_rounds: int = 2
    repair: bool = True
    timeout: int = 900
    watch_seconds: int = 20
    env: dict[str, str] = field(default_factory=dict)
    out_dir: Path = Path("runs")

    def public(self) -> dict:
        # secrets stay out of reports, only the variable names are recorded
        return {
            "sandbox": self.sandbox, "image": self.image, "offline": self.offline,
            "max_rounds": self.max_rounds, "repair": self.repair, "timeout": self.timeout,
            "watch_seconds": self.watch_seconds, "env_keys": sorted(self.env),
        }


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "project"


def _short(cmd: str, width: int = 70) -> str:
    one = " ".join(cmd.split())
    return one if len(one) <= width else one[: width - 3] + "..."


def _skip_supplied_secrets(plan: Plan, env: dict[str, str]) -> Plan:
    """`export KEY=your_key_here` would clobber a real value the user handed us."""
    if not env:
        return plan
    kept, skipped = [], list(plan.skipped)
    for step in plan.steps:
        m = re.match(r"^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)=", step.command)
        if m and m.group(1) in env and "\n" not in step.command.strip():
            skipped.append(Skipped(step.command, f"{m.group(1)} supplied to FirstRun", step.line))
            continue
        kept.append(step)
    steps = [replace(s, index=i) for i, s in enumerate(kept, 1)]
    return replace(plan, steps=steps, skipped=skipped)


def _provider(llm: LLM) -> str:
    # ai.py labels its output "gemini"; report the provider that actually answered
    return llm.name.split(":", 1)[0] or "gemini"


def understand(project_dir: Path, llm: Optional[LLM], env: dict[str, str]) -> Plan:
    plan = extract_plan(project_dir)
    if llm is not None:
        from .ai import ai_extract_plan

        plan = ai_extract_plan(llm, project_dir, plan)
        if plan.engine == "gemini":
            plan.engine = _provider(llm)
        readme = find_readme(project_dir)
        if readme is not None:
            plan = apply_directives(plan, read_text(readme) or "")
    return _skip_supplied_secrets(plan, env)


def investigate(
    project_dir: Path, plan: Plan, run: RunResult, llm: Optional[LLM],
    history: list[Round], on_event: EventFn,
) -> Diagnosis:
    hint = rules.diagnose(project_dir, plan, run)
    if llm is not None:
        from .ai import ai_investigate

        diag = ai_investigate(llm, project_dir, plan, run, hint=hint, history=history, on_event=on_event)
        if diag.engine == "gemini":
            diag.engine = _provider(llm)
        return diag
    if hint is not None:
        return hint
    failed = run.failed_step
    return Diagnosis(
        category="unknown",
        summary="The failure does not match any offline rule. Run with an AI key (Groq or Gemini) for a deeper look.",
        explanation=(failed.output.strip().splitlines() or ["no output"])[-1] if failed else "",
        confidence="low",
    )


def _signature(run: RunResult) -> tuple[str, str]:
    failed = run.failed_step
    if failed is None:
        return ("", "")
    lines = [ln for ln in failed.output.strip().splitlines() if ln.strip()]
    return (" ".join(failed.step.command.split()), lines[-1] if lines else "")


def _final_run(report: Report) -> Optional[RunResult]:
    for r in reversed(report.rounds):
        if r.verification is not None:
            return r.verification
    return report.documented_run


def _output_check(plan: Plan, run: RunResult, llm: Optional[LLM]) -> Optional[dict]:
    if not plan.expected_output:
        return None
    candidates = [r for r in run.results if r.ok and r.step.kind == "run" and r.output.strip()]
    if not candidates:
        candidates = [r for r in run.results if r.ok and r.output.strip()]
    if not candidates:
        return None
    from .ai import ai_output_check

    check = ai_output_check(llm, plan.expected_output, candidates[-1].output)
    check["command"] = candidates[-1].step.command
    return check


def _headline(report: Report) -> str:
    doc = report.documented_run
    failed = doc.failed_step if doc else None
    where = f"step {failed.step.index} (`{_short(failed.step.command)}`)" if failed else "setup"
    if report.verdict == "passed":
        n = len(doc.results) if doc else 0
        return f"Works as documented: all {n} steps passed in a fresh sandbox."
    if report.verdict == "fixed":
        last = report.rounds[-1]
        changes = sum(len(r.diagnosis.edits) for r in report.rounds)
        return (
            f"As documented, setup fails at {where}. The suggested fix ({changes} change"
            f"{'s' if changes != 1 else ''}) passed from scratch in a fresh sandbox"
            f" ({len(last.verification.results)} steps)."
        )
    if report.verdict == "blocked":
        reason = next((r.diagnosis for r in reversed(report.rounds) if r.diagnosis.blocked), None)
        if reason is not None and reason.category != "credentials_required":
            return f"Blocked: {reason.summary} FirstRun stopped instead of faking a result."
        # missing_env is ranked by the rules (key named in the error first), keep that order
        keys = list(dict.fromkeys(k for r in report.rounds for k in r.diagnosis.missing_env))
        names = ", ".join(keys[:2]) + (f" and {len(keys) - 2} more" if len(keys) > 2 else "") if keys else "an API key"
        return f"Blocked: credentials required ({names}). FirstRun stopped instead of faking a result."
    if report.verdict == "failed":
        summary = report.rounds[-1].diagnosis.summary if report.rounds else "no diagnosis"
        return f"As documented, setup fails at {where}. No verified fix: {summary}"
    return f"FirstRun could not finish: {report.error}"


class _Recorder:
    """Passes events through and keeps a copy, so a finished run can be replayed in the UI."""

    def __init__(self, on_event: EventFn, t0: float):
        self.on_event, self.t0, self.events = on_event, t0, []

    def __call__(self, kind: str, message: str, data: Optional[dict] = None) -> None:
        self.events.append({"seq": len(self.events), "t": round(time.time() - self.t0, 3),
                            "kind": kind, "message": message, "data": data})
        self.on_event(kind, message, data)


def _pick_environment(project_dir: Path, plan: Plan, settings: Settings, sandbox, report: Report,
                      emit: EventFn) -> bool:
    """Match the container to the project (Node needs Node). Only when the user left --image alone.

    Returns True when every plan needs a FirstRun provided Node install step in front.
    """
    if settings.sandbox != "docker":
        return False
    image, install_node, reason = pick_image(project_dir, plan.steps, settings.image)
    if reason is None:
        return False
    sandbox.image = image
    report.settings["image"] = image
    report.settings["image_reason"] = reason
    report.settings["sandbox_detail"] = sandbox.describe()
    emit("info", f"Environment: {reason}", {"image": image, "install_node": install_node})
    return install_node


def _adapt(plan: Plan, install_node: bool, reason: Optional[str]) -> Plan:
    if install_node:
        plan.steps = node_prerequisite(plan.steps)
    if reason and not any(n.startswith("Environment:") for n in plan.notes):
        plan.notes.append(f"Environment: {reason}.")
    return plan


def _run(sandbox, project_dir: Path, plan: Plan, settings: Settings, label: str, emit: EventFn) -> RunResult:
    run = sandbox.run(project_dir, plan.steps, env=settings.env, label=label, on_event=emit,
                      timeout=settings.timeout)
    failed = run.failed_step
    if failed is not None and rules.is_network_flake(failed.output):
        emit("warn", "The sandbox lost its connection to the package index, retrying once", None)
        run = sandbox.run(project_dir, plan.steps, env=settings.env, label=label, on_event=emit,
                          timeout=settings.timeout)
        failed = run.failed_step
        if failed is not None and rules.is_network_flake(failed.output):
            run.status = "error"
            run.error = (f"network problem: step {failed.step.index} could not reach the package index "
                         "twice in a row, so this says nothing about the README. Check the connection "
                         "(or Docker's network) and run again.")
    _accept_documented_exit(run, plan, project_dir, emit)
    return run


def _accept_documented_exit(run: RunResult, plan: Plan, project_dir: Path, emit: EventFn) -> bool:
    """A last step that exits 1 or 2 the way the README's example shows counts as passed.

    Demo commands such as a linter run on a broken example exit non-zero on purpose. Only the
    last step qualifies (nothing after it was skipped), and only without a Python traceback.
    """
    failed = run.failed_step
    if failed is None or failed.status != "failed" or failed.exit_code not in (1, 2):
        return False
    if failed is not run.results[-1] or rules.TRACEBACK_RE.search(failed.output):
        return False
    readme = find_readme(project_dir)
    text = (read_text(readme) or "") if readme else ""
    documented = documented_output(text, failed.step.line) if text else None
    if not documented and plan.expected_output:
        documented = plan.expected_output
    if not documented:
        return False
    score = rules.output_similarity(documented, failed.output)
    if score < 0.5:
        return False
    failed.status = "passed"
    run.status = "passed"
    note = (f"Step {failed.step.index} exits {failed.exit_code}, but the non-zero exit matches the "
            f"documented example (similarity {score:.2f}), so it counts as passed.")
    if note not in plan.notes:
        plan.notes.append(note)
    emit("info", note, {"index": failed.step.index, "exit_code": failed.exit_code})
    return True


def run_check(
    target: str, settings: Settings, *, subdir: Optional[str] = None,
    on_event: EventFn = noop_event, run_dir: Optional[Path] = None,
) -> tuple[Report, Path]:
    """Check one project. run_dir lets a caller (the web UI) pick the output folder up front."""
    started, t0 = _now(), time.time()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    emit = _Recorder(on_event, t0)

    def stage(name: str, state: str) -> None:
        emit("stage", f"{name} {state}", {"stage": name, "state": state})

    def finish() -> tuple[Report, Path]:
        return _finish(report, settings, stamp, t0, emit, stage, run_dir)

    report = Report(
        project=Path(subdir or target.rstrip("/")).name or target, source=target,
        started_at=started, finished_at="", verdict="error", headline="",
        documented_plan=None, documented_run=None, settings=settings.public(),
    )

    with tempfile.TemporaryDirectory(prefix="firstrun-") as tmp:
        tmp_dir = Path(tmp)
        try:
            stage("understand", "start")
            project_dir, report.source = resolve_target(target, subdir, tmp_dir)
            report.project = project_dir.name
            sandbox = make_sandbox(settings.sandbox, image=settings.image, watch_seconds=settings.watch_seconds)
            ok, why = sandbox.available()
            if not ok:
                raise SourceError(why)
            report.settings["sandbox_detail"] = sandbox.describe()

            llm = None if settings.offline else get_llm()
            report.settings["engine"] = llm.name if llm else "rules (offline)"
            if llm is None and not settings.offline:
                emit("warn", "No GEMINI_API_KEY, GOOGLE_API_KEY or GROQ_API_KEY found, using the offline rules", None)

            plan = understand(project_dir, llm, settings.env)
            install_node = _pick_environment(project_dir, plan, settings, sandbox, report, emit)
            plan = _adapt(plan, install_node, report.settings.get("image_reason"))
            report.documented_plan = plan
            report.static_hints = rules.static_hints(project_dir)
            emit("plan", f"Plan: {len(plan.steps)} steps from {plan.readme_path or 'no README'}"
                         f" ({len(plan.skipped)} line{'' if len(plan.skipped) == 1 else 's'} skipped, planner: {plan.engine})",
                 {"label": "as documented", "plan": to_dict(plan)})
            if not plan.steps:
                stage("understand", "fail")
                report.verdict = "failed"
                report.rounds.append(Round(1, Diagnosis(
                    category="undocumented_step",
                    summary="The README has no setup or run commands a newcomer could follow.",
                    confidence="high",
                )))
                return finish()
            stage("understand", "done")

            stage("attempt", "start")
            documented = _run(sandbox, project_dir, plan, settings, "as documented", emit)
            report.documented_run = documented
            report.settings["sandbox_detail"] = documented.sandbox  # reflects a git layer fallback
            if documented.status == "error":
                raise SourceError(documented.error or "the sandbox failed to start")
            stage("attempt", "done" if documented.status == "passed" else "fail")

            if documented.status == "passed":
                report.verdict = "passed"
                report.output_check = _output_check(plan, documented, llm)
                return finish()

            patched = copy_project(project_dir, tmp_dir / "patched" / project_dir.name)
            cur_dir, cur_plan, cur_run = project_dir, plan, documented
            report.verdict = "failed"
            for n in range(1, max(1, settings.max_rounds) + 1):
                stage("investigate", "start")
                diag = investigate(cur_dir, cur_plan, cur_run, llm, report.rounds, emit)
                rnd = Round(number=n, diagnosis=diag)
                report.rounds.append(rnd)
                emit("diagnosis", diag.summary, {"round": n, "diagnosis": to_dict(diag)})
                stage("investigate", "done")
                if diag.blocked:
                    report.verdict = "blocked"
                    break
                if not settings.repair or not diag.edits:
                    break

                stage("repair", "start")
                try:
                    apply_edits(patched, diag.edits)
                except EditError as exc:
                    diag.explanation += f"\n\nThe proposed edit could not be applied: {exc}"
                    stage("repair", "fail")
                    break
                rnd.diff = unified_diff(project_dir, patched)
                emit("diff", f"{len(diag.edits)} edit(s) applied to a copy", {"round": n, "diff": rnd.diff})
                stage("repair", "done")

                stage("verify", "start")
                new_plan = _adapt(understand(patched, llm, settings.env), install_node,
                                  report.settings.get("image_reason"))
                rnd.plan = new_plan
                emit("plan", f"Re-read the patched README: {len(new_plan.steps)} steps",
                     {"label": f"after fix {n}", "plan": to_dict(new_plan)})
                rnd.verification = _run(sandbox, patched, new_plan, settings, f"after fix {n}", emit)
                if rnd.verification.status == "error":
                    stage("verify", "fail")
                    report.verdict = "error"
                    report.error = rnd.verification.error
                    break
                if rnd.verification.status == "passed":
                    stage("verify", "done")
                    report.verdict = "fixed"
                    report.output_check = _output_check(new_plan, rnd.verification, llm)
                    break
                stage("verify", "fail")
                if _signature(rnd.verification) == _signature(cur_run):
                    emit("warn", "The fix did not change the failure, stopping", None)
                    break
                cur_dir, cur_plan, cur_run = patched, new_plan, rnd.verification

            if report.verdict == "failed":
                last = _final_run(report)
                failed = last.failed_step if last else None
                missing = rules.detect_credentials(failed.output, cur_dir) if failed else None
                if missing is not None:
                    report.verdict = "blocked"
                    if report.rounds and not report.rounds[-1].diagnosis.missing_env:
                        report.rounds[-1].diagnosis.missing_env = missing
            # rounds carry cumulative diffs, so the latest one is the whole change
            report.final_diff = next((r.diff for r in reversed(report.rounds) if r.diff), "")
            return finish()

        except SourceError as exc:
            report.verdict = "error"
            report.error = str(exc)
            emit("warn", str(exc), None)
            return finish()


def _metrics(report: Report) -> dict:
    plan, doc = report.documented_plan, report.documented_run
    final = _final_run(report)
    failed = doc.failed_step if doc else None
    return {
        "time_to_first_success": round(final.duration, 1) if final and report.verdict in ("passed", "fixed") else None,
        "documented_seconds": round(doc.duration, 1) if doc else None,
        "failed_at_step": failed.step.index if failed else None,
        "steps_documented": len(plan.steps) if plan else 0,
        "skipped_lines": len(plan.skipped) if plan else 0,
        "rounds": len(report.rounds),
        "fixes_applied": sum(len(r.diagnosis.edits) for r in report.rounds if r.diff),
        "sandbox_runs": (1 if doc else 0) + sum(1 for r in report.rounds if r.verification),
        "total_seconds": report.settings.get("duration_seconds"),
    }


def _finish(report: Report, settings: Settings, stamp: str, t0: float, emit: "_Recorder", stage,
            run_dir: Optional[Path]) -> tuple[Report, Path]:
    report.finished_at = _now()
    report.settings["duration_seconds"] = round(time.time() - t0, 1)
    report.headline = _headline(report)
    report.metrics = _metrics(report)
    stage("report", "start")
    run_dir = Path(run_dir) if run_dir else Path(settings.out_dir) / f"{stamp}-{_slug(report.project)}"
    write_report(report, run_dir)
    stage("report", "done")
    emit("done", report.headline, {"verdict": report.verdict, "run_dir": str(run_dir)})
    write_events(emit.events, run_dir)
    return report, run_dir
