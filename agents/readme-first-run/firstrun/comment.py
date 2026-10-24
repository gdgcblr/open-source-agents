"""Short PR comment and README badge versions of a Report."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import quote

from .models import Report, RunResult

MARKER = "<!-- firstrun-report -->"
MAX_COMMENT_CHARS = 60_000  # GitHub rejects comments over 65,536
MAX_DIFF_CHARS = 6_000
OUTPUT_LINES = 8

STATUS_WORD = {
    "passed": "PASSED",
    "fixed": "FIXED",
    "blocked": "BLOCKED",
    "failed": "FAILED",
    "error": "ERROR",
}

BADGES = {
    "passed": ("works as documented", "brightgreen"),
    "fixed": ("fix available", "yellow"),
    "blocked": ("needs credentials", "lightgrey"),
    "failed": ("broken", "red"),
    "error": ("not checked", "lightgrey"),
}


def _one_line(text: str, width: int = 80) -> str:
    one = " ".join(str(text).split())
    return one if len(one) <= width else one[: width - 3] + "..."


def _code(text: str, width: int = 80) -> str:
    # backticks inside inline code would break the markdown
    return "`" + _one_line(text, width).replace("`", "'") + "`"


def _tail(text: str, lines: int = OUTPUT_LINES) -> str:
    rows = [r for r in text.rstrip().splitlines()]
    return "\n".join(rows[-lines:]).replace("```", "'''")


def _project_path(report: Report, project_path: Optional[str]) -> Optional[str]:
    if project_path:
        return project_path.strip("/")
    # in the event monorepo the checked folder is agents/<slug> or tools/<slug>, either as the
    # end of the path / tree URL or as the "(subdir)" suffix the source label gets
    source = (report.source or "").strip()
    m = re.search(r"\(((?:agents|tools)/[^/\s()]+)/?\)$", source) or \
        re.search(r"(?:^|/)((?:agents|tools)/[^/\s()]+)/?$", source)
    return m.group(1) if m else None


def _truncate_diff(diff: str, limit: int) -> str:
    if len(diff) <= limit:
        return diff.rstrip()
    lines = diff.rstrip().splitlines()
    kept, size = [], 0
    for line in lines:
        if size + len(line) + 1 > limit:
            break
        kept.append(line)
        size += len(line) + 1
    rest = len(lines) - len(kept)
    return "\n".join(kept) + f"\n... diff truncated, {rest} more lines in fix.patch"


def _steps_table(run: RunResult) -> list[str]:
    out = ["| # | Command | Status | Exit | Time |", "|---|---|---|---|---|"]
    for r in run.results:
        code = "" if r.exit_code is None else str(r.exit_code)
        cmd = _code(r.step.command, 60).replace("|", "\\|")
        out.append(f"| {r.step.index} | {cmd} | {r.status} | {code} | {r.duration:.1f}s |")
    return out


def _documented_line(run: Optional[RunResult]) -> list[str]:
    if run is None:
        return []
    failed = run.failed_step
    if failed is None:
        if run.status == "passed":
            return [f"**As documented:** all {len(run.results)} steps passed ({run.duration:.0f}s)."]
        if run.error:
            return [f"**As documented:** the sandbox did not start: {_one_line(run.error, 200)}"]
        return [f"**As documented:** {run.status}."]
    where = f" (README line {failed.step.line})" if failed.step.line else ""
    if failed.status == "timeout":
        what = "timed out"
    elif failed.exit_code is not None:
        what = f"failed with exit {failed.exit_code}"
    else:
        what = "failed"
    out = [f"**As documented:** step {failed.step.index} {_code(failed.step.command)}{where} {what}."]
    tail = _tail(failed.output)
    if tail:
        out += ["", "```text", tail, "```"]
    return out


def _diagnosis_lines(report: Report) -> list[str]:
    out = []
    many = len(report.rounds) > 1
    for rnd in report.rounds:
        d = rnd.diagnosis
        label = f"**Why (round {rnd.number}):**" if many else "**Why:**"
        out += ["", f"{label} {d.summary.strip()}"]
        for ev in d.evidence[:5]:
            loc = f"{ev.file}:{ev.line}" if ev.line else ev.file
            out.append(f"- `{loc}` {ev.note.strip()}")
        if len(d.evidence) > 5:
            out.append(f"- and {len(d.evidence) - 5} more in the full report")
    missing = sorted({k for r in report.rounds for k in r.diagnosis.missing_env})
    if missing:
        names = ", ".join(f"`{k}`" for k in missing)
        out += ["", f"Needs {names}. Nothing was faked: re-run FirstRun with the value supplied "
                    "(`--env-file` or `--pass-env`) to check the rest of the setup."]
    return out


def _verification_line(report: Report) -> str:
    last = next((r.verification for r in reversed(report.rounds) if r.verification is not None), None)
    if report.verdict == "fixed" and last is not None:
        return (f"Verified: with this patch the README ran from scratch in a second fresh sandbox "
                f"({len(last.results)} steps passed).")
    if last is not None and last.failed_step is not None:
        f = last.failed_step
        return f"Not verified: with this patch the setup still stops at step {f.step.index} {_code(f.step.command, 60)}."
    return "Not verified: FirstRun could not run the patched setup, so please review it by hand."


def _patch_lines(report: Report, project_path: Optional[str], diff_limit: int) -> list[str]:
    if not report.final_diff.strip():
        return []
    out = ["", "Suggested change:", "", "```diff", _truncate_diff(report.final_diff, diff_limit), "```", "",
           _verification_line(report)]
    path = _project_path(report, project_path)
    if path:
        out.append(f"Apply it from the repo root with `git apply --directory={path} fix.patch`.")
    else:
        out.append("Apply it with `git apply fix.patch` (add `--directory=<project folder>` when the project "
                   "is not the repo root).")
    return out


def _details_lines(report: Report) -> list[str]:
    runs = [report.documented_run] + [r.verification for r in report.rounds]
    runs = [r for r in runs if r is not None and r.results]
    if not runs:
        return []
    out = ["", "<details><summary>Steps FirstRun ran</summary>", ""]
    for run in runs:
        out += [f"**{run.label}** ({run.sandbox}, {run.status})", ""] + _steps_table(run) + [""]
    plan = report.documented_plan
    if plan is not None and plan.skipped:
        out += ["Skipped README lines:", ""]
        for s in plan.skipped:
            where = f" (line {s.line})" if s.line else ""
            out.append(f"- {_code(s.command, 60)}{where}: {s.reason}")
        out.append("")
    out.append("</details>")
    return out


def _footer(report: Report) -> str:
    s = report.settings or {}
    bits = []
    sandbox = s.get("sandbox_detail") or s.get("sandbox")
    if sandbox:
        bits.append(f"sandbox: {sandbox}")
    if s.get("engine"):
        bits.append(f"reasoning: {s['engine']}")
    if s.get("duration_seconds") is not None:
        bits.append(f"{s['duration_seconds']}s")
    extra = f" ({', '.join(bits)})" if bits else ""
    return f"<sub>Checked by FirstRun{extra}. The full report, logs and fix.patch are in the run artifacts.</sub>"


def _build(report: Report, project_path: Optional[str], diff_limit: int, details: bool) -> str:
    word = STATUS_WORD.get(report.verdict, (report.verdict or "unknown").upper())
    out = [MARKER, f"**FirstRun: {word}** for `{report.project or 'project'}`", ""]
    if report.headline:
        out.append(report.headline.strip())
    if report.verdict == "error" and report.error and report.error not in (report.headline or ""):
        out += ["", f"Error: {_one_line(report.error, 300)}"]
    doc = _documented_line(report.documented_run)
    if doc:
        out += [""] + doc
    out += _diagnosis_lines(report)
    out += _patch_lines(report, project_path, diff_limit)
    if details:
        out += _details_lines(report)
    out += ["", _footer(report), ""]
    return "\n".join(out)


def render_comment(report: Report, project_path: Optional[str] = None) -> str:
    """Compact markdown for a PR comment. The first line is a marker so a bot can update it."""
    body = _build(report, project_path, MAX_DIFF_CHARS, details=True)
    if len(body) > MAX_COMMENT_CHARS:
        body = _build(report, project_path, MAX_DIFF_CHARS, details=False)
    if len(body) > MAX_COMMENT_CHARS:
        body = _build(report, project_path, 1_000, details=False)
    if len(body) > MAX_COMMENT_CHARS:
        body = body[: MAX_COMMENT_CHARS - 80].rstrip() + "\n\n... comment truncated, see report.md\n"
    return body


def _shield(text: str) -> str:
    # shields.io static badges use -- for a dash and __ for an underscore
    return quote(text.replace("-", "--").replace("_", "__"), safe="")


def render_badge(report: Report, link: Optional[str] = None) -> str:
    """Markdown for a shields.io badge, optionally linked to the report."""
    message, color = BADGES.get(report.verdict, ("unknown", "lightgrey"))
    url = f"https://img.shields.io/badge/{_shield('FirstRun')}-{_shield(message)}-{color}"
    image = f"![FirstRun: {message}]({url})"
    return f"[{image}]({link})" if link else image
