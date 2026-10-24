"""Runs every registered check against one project folder and builds the Report.

This is the single entry point that every front end (CLI today; MCP server,
GitHub Action and fix-mode agent later) calls.
"""

from __future__ import annotations

import time
import traceback
from pathlib import Path

from . import __version__
from .context import ProjectContext, SkipCheck, build_context
from .models import CheckResult, Finding, Metrics, Report, Severity, Status, Summary
from .registry import CheckSpec, all_checks
from .rules import Rules, load_rules


def _status_for(findings: list[Finding]) -> Status:
    if not findings:
        return Status.PASS
    worst = max(f.severity.rank for f in findings)
    return {3: Status.FAIL, 2: Status.WARN, 1: Status.INFO}[worst]


def run_check(spec: CheckSpec, ctx: ProjectContext) -> CheckResult:
    base = dict(id=spec.id, group=spec.group, title=spec.title)
    try:
        findings = list(spec.func(ctx))
    except SkipCheck as skip:
        return CheckResult(**base, status=Status.SKIP, skip_reason=str(skip))
    except Exception as exc:  # a bug in prcheck must never look like a pass
        detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        return CheckResult(**base, status=Status.CRASH, skip_reason=f"Internal error: {detail}")
    return CheckResult(**base, status=_status_for(findings), findings=findings)


def summarize(results: list[CheckResult], *, strict: bool) -> Summary:
    summary = Summary(strict=strict)
    for result in results:
        for f in result.findings:
            if f.severity is Severity.ERROR:
                summary.errors += 1
            elif f.severity is Severity.WARN:
                summary.warnings += 1
            else:
                summary.infos += 1
        if result.status is Status.PASS or result.status is Status.INFO:
            summary.passed += 1
        elif result.status is Status.FAIL:
            summary.failed += 1
        elif result.status is Status.WARN:
            summary.warned += 1
        elif result.status is Status.SKIP:
            summary.skipped += 1
        else:
            summary.crashed += 1
    summary.ready = summary.errors == 0 and summary.crashed == 0 and (not strict or summary.warnings == 0)
    return summary


def run(project_dir: Path, *, base: str | None = None, strict: bool = False, use_git: bool = True,
        rules: Rules | None = None, only: set[str] | None = None) -> tuple[Report, ProjectContext]:
    started = time.perf_counter()
    rules = rules or load_rules()
    ctx = build_context(project_dir, rules, base=base, use_git=use_git)
    specs = [s for s in all_checks() if only is None or s.id in only]
    results = [run_check(spec, ctx) for spec in specs]

    report = Report(
        tool_version=__version__,
        target=ctx.display_path,
        category=ctx.category,
        slug=ctx.slug,
        repo_root=ctx.repo_root.as_posix() if ctx.repo_root else None,
        file_mode=ctx.file_mode,
        base=ctx.scope.base if ctx.scope else None,
        template_source=ctx.template_source,
        checks=results,
        summary=summarize(results, strict=strict),
        metrics=Metrics(
            duration_ms=int((time.perf_counter() - started) * 1000),
            files_listed=len(ctx.files),
            files_scanned=ctx.files_scanned,
            bytes_scanned=ctx.bytes_scanned,
        ),
    )
    return report, ctx
