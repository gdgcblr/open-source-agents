"""Terminal summary, report.json, and report.md. User-facing text is plain prose;
caveman-style model notes stay in report.json under internal_notes."""

from __future__ import annotations

import sys
from pathlib import Path

from rce_sentinel.models import Finding, ScanReport

COLORS = {"critical": "\033[1;31m", "high": "\033[31m", "medium": "\033[33m",
          "low": "\033[2m"}
RESET = "\033[0m"


def _c(label: str, text: str, tty: bool) -> str:
    return f"{COLORS.get(label, '')}{text}{RESET}" if tty else text


def _visible(report: ScanReport) -> list[Finding]:
    return [f for f in report.findings if (f.risk and f.risk.label != "low") or f.realert]


def terminal(report: ScanReport, stream=None) -> str:  # type: ignore[no-untyped-def]
    stream = stream or sys.stderr
    tty = hasattr(stream, "isatty") and stream.isatty()
    s = report.stats
    out = [f"rce-sentinel {report.mode}: {len(report.findings)} finding(s), "
           f"{s.llm_calls} LLM call(s), {s.cache_hits} cache hit(s), "
           f"${s.cost_usd:.5f}, {report.duration_s:.2f}s"]
    for d in report.degraded:
        out.append(f"  ! degraded: {d}")
    shown = _visible(report)
    for f in shown:
        label = f.risk.label if f.risk else "low"
        tag = _c(label, f"[{label.upper():8}]", tty)
        sup = " (suppressed)" if f.suppressed else ""
        out.append(f"  {tag} {f.file}:{f.line} {f.rule_id} {f.title}{sup}")
        out.append(f"             how an attacker gets RCE here: {f.attacker_path}")
        if f.realert:
            out.append(f"             re-alert: {f.realert}")
        if f.fix:
            out.append(f"             fix: {f.fix}")
        out.append(f"             decided by: {f.decided_by}")
    hidden = len(report.findings) - len(shown)
    if hidden:
        out.append(f"  ({hidden} low-risk finding(s) in report.json)")
    if report.blocked:
        out.append(_c("critical", "COMMIT BLOCKED: high-risk RCE finding above.", tty))
        out.append("  Fix it, or bypass once with `git commit --no-verify` "
                   "(the post-commit scan will still report it).")
    text = "\n".join(out)
    print(text, file=stream)
    return text


def markdown(report: ScanReport) -> str:
    s = report.stats
    lines = [f"# rce-sentinel report ({report.mode})", "",
             f"- Run: `{report.run_id}` at {report.started}, {report.duration_s:.2f}s",
             f"- Findings: {len(report.findings)}; blocked: {report.blocked}",
             f"- LLM calls: {s.llm_calls}; cache hits: {s.cache_hits}; cost: ${s.cost_usd:.5f}",
             f"- Versions: rules `{report.versions.get('rules')}`, "
             f"CVE db `{report.versions.get('cve_db')}`, "
             f"prompts `{report.versions.get('prompt')}`"]
    if report.degraded:
        lines += ["", "## Degraded mode", *[f"- {d}" for d in report.degraded]]
    lines += ["", "## Findings", "",
              "| Risk | Location | Rule | How an attacker gets RCE here |",
              "| :--- | :--- | :--- | :--- |"]
    for f in report.findings:
        label = f"{f.risk.label} {f.risk.score}" if f.risk else "-"
        path = f.attacker_path.replace("|", "\\|")
        lines.append(f"| {label} | `{f.file}:{f.line}` | {f.rule_id} | {path} |")
    lines += ["", "## Details", ""]
    for f in report.findings:
        lines.append(f"### {f.rule_id} at `{f.file}:{f.line}`")
        lines.append(f"- {f.title} ({f.cwe})")
        if f.snippet:
            lines.append(f"- Code: `{f.snippet.replace('`', '')}`")
        if f.taint_chain:
            lines.append(f"- Data flow: {' → '.join(f.taint_chain)}")
        if f.dependency:
            d = f.dependency
            lines.append(f"- Dependency: {d.ecosystem} {d.name} {d.version} ({d.file})")
            lines.append(f"- Reachable: {f.reachable} ({'; '.join(f.reach_evidence)})")
        if f.risk:
            lines.append(f"- Risk factors: {f.risk.factors}")
        if f.realert:
            lines.append(f"- Re-alert: {f.realert}")
        lines.append(f"- Fix: {f.fix}")
        lines.append(f"- Decided by: {f.decided_by}")
        lines.append("")
    return "\n".join(lines)


def write(report: ScanReport, state_dir: Path) -> tuple[Path, Path]:
    state_dir.mkdir(parents=True, exist_ok=True)
    jpath = state_dir / "report.json"
    mpath = state_dir / "report.md"
    jpath.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    mpath.write_text(markdown(report), encoding="utf-8")
    return jpath, mpath
