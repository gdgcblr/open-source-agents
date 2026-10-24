"""Developer-friendly Markdown PR comment formatter."""
from securepr.models import ScanReport


def render_markdown_report(report: ScanReport) -> str:
    gate_status = "PASSED" if report.passed_gate else "FAILED"
    gate_icon = "white_check_mark" if report.passed_gate else "x"

    md = []
    md.append(f"## SecurePR AI Security Review Results - :{gate_icon}: `{gate_status}`\n")
    md.append(f"**Target:** `{report.target_commit_or_branch}` | **Total Findings:** `{report.total_findings}` | **Redacted Elements:** `{report.redacted_item_count}`\n")

    if report.attack_path_hypotheses:
        md.append("### Inferred Attack Path Hypotheses")
        md.append("> *Hypotheses correlate related findings across multiple files.*")
        for hyp in report.attack_path_hypotheses:
            md.append(f"#### [{hyp.id}] {hyp.title} (`{hyp.stride.value}`)")
            md.append(f"{hyp.summary}\n")
            md.append("**Attack Steps:**")
            for step in hyp.steps:
                md.append(f"{step.step_number}. `{step.file_path}`: {step.action_or_state}")
            md.append("")

    md.append("### Prioritized Vulnerability Findings\n")
    if not report.prioritized_findings:
        md.append("No security weaknesses identified in this pull request change set.")
        return "\n".join(md)

    for item in report.prioritized_findings:
        f = item.finding
        r = item.risk
        badge = f"**[{r.priority_level.value} - {r.numeric_score}/10]**"

        md.append(f"#### {badge} {f.id}: {f.title}")
        md.append(f"- **Category:** `{f.category.value}` | **STRIDE:** `{[s.value for s in f.stride]}`")
        if f.owasp_api_category:
            md.append(f"- **OWASP Benchmark:** `{f.owasp_api_category}`")
        md.append(f"- **Risk Context:** {r.rationale}")

        md.append("\n**Evidence:**")
        for ev in f.evidence:
            md.append(f"`{ev.file_path}:{ev.start_line}-{ev.end_line}`")
            md.append("```python")
            md.append(ev.snippet)
            md.append("```")

        md.append(f"**Remediation Guidance:**\n{f.remediation_hint}")
        if item.ai_explanation:
            md.append(f"\n> **AI Contextual Analysis:**\n> {item.ai_explanation}")
        md.append("\n---\n")

    return "\n".join(md)
