"""Readable terminal and Markdown reporting."""
from collections import Counter
from pathlib import Path

def render_markdown(findings, ai_analysis: str | None = None) -> str:
    counts = Counter(f.severity for f in findings)
    lines = ["# VulnPilot Scan Report", "", f"**Findings:** {len(findings)}", "", "## Severity Summary", ""]
    if counts:
        lines.extend(f"- **{severity}:** {count}" for severity, count in sorted(counts.items()))
    else:
        lines.append("- No findings reported.")
    lines += ["", "## Findings", ""]
    if not findings:
        lines.append("No findings.")
    for index, finding in enumerate(findings, 1):
        lines += [f"### {index}. [{finding.severity}] `{finding.rule_id}`", "",
                  f"- **Location:** `{finding.path}:{finding.line}:{finding.column}`",
                  f"- **Message:** {finding.message}"]
        if finding.reference:
            lines.append(f"- **Reference:** {finding.reference}")
        lines.append("")
    if ai_analysis:
        lines += ["## Optional AI Triage", "", ai_analysis, "",
                  "> AI output is advisory. Verify findings and review fixes manually."]
    lines += ["", "## Safety", "",
              "VulnPilot reports findings and recommendations only. It does not edit source files or apply patches.", ""]
    return "\n".join(lines)

def print_summary(findings) -> None:
    print(f"\nVulnPilot: {len(findings)} finding(s)")
    if not findings:
        print("No findings reported.")
    for finding in findings:
        print(f"[{finding.severity:<8}] {finding.path}:{finding.line}:{finding.column}  {finding.rule_id}")
        print(f"           {finding.message}")

def save_report(path: str | Path, findings, ai_analysis: str | None = None) -> None:
    Path(path).expanduser().write_text(render_markdown(findings, ai_analysis), encoding="utf-8")
