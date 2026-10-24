"""Writes preflight-report.md from a preflight() result."""
from pathlib import Path

from checks import redact


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def write_report(result: dict, out_dir=".") -> Path:
    icon = "✅" if result["verdict"] == "PASS" else "❌"
    lines = [f"# PR Preflight report: {icon} {result['verdict']}", "",
             f"Project: `{result['project']}`  ", f"Tool calls: {result['calls']}", ""]
    if result["reasons"]:
        lines += ["## Why it failed", ""] + [f"- {r}" for r in result["reasons"]] + [""]
    if result["warnings"]:
        lines += ["## Warnings", ""] + [f"- {w}" for w in result["warnings"]] + [""]

    lines += ["## Checks", "", "| Check | Status | Details |", "|---|---|---|"]
    for c in result["checks"]:
        mark = "✅" if c["status"] == "pass" else "❌"
        lines.append(f"| {c['id']} | {mark} | {_cell(c['message'])} |")

    lines += ["", "## Commands run", ""]
    if result["runs"]:
        lines += ["| Command | Exit code |", "|---|---|"]
        lines += [f"| `{_cell(r['command'])}` | {r['exit_code']} |" for r in result["runs"]]
    else:
        lines.append("_No commands were run._")

    lines += ["", "## Blocked commands (security)", ""]
    if result["blocked"]:
        lines += ["| Tool | Args | Reason |", "|---|---|---|"]
        lines += [f"| {b['tool']} | `{_cell(b['args'])}` | {_cell(b['reason'])} |"
                  for b in result["blocked"]]
    else:
        lines.append("_None._")

    lines += ["", "## Agent diagnosis", "", redact(result["diagnosis"] or "_No diagnosis._"), ""]

    fixes = [f"**{c['id']}**: {c['fix']}" for c in result["checks"] if c["status"] == "fail"]
    if any(r["exit_code"] != 0 for r in result["runs"]):
        fixes.append("**Run failure**: see the agent diagnosis above for the root cause and fix.")
    lines += ["## Suggested fixes", ""] + ([f"- {f}" for f in fixes] or ["_Nothing to fix._"])

    path = Path(out_dir) / "preflight-report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
