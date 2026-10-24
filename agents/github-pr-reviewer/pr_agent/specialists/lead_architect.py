from typing import List, Tuple
from ..models import SpecialistVerdict, TriageResult, ReviewIssue


class LeadArchitectAgent:
    """Council Chair agent that synthesizes specialist reports into a definitive merge verdict."""

    def __init__(self, name: str = "Lead Software Architect"):
        self.name = name

    def adjudicate(
        self,
        triage: TriageResult,
        specialist_verdicts: List[SpecialistVerdict],
        all_issues: List[ReviewIssue]
    ) -> Tuple[str, int, str, List[str]]:
        """
        Adjudicate final PR verdict, composite health score, and executive rationale.
        Returns: (verdict, health_score, executive_summary, recommendations)
        """
        # Weighted Health Score: Security (45%), Performance (30%), Testing/Quality (25%)
        sec_verdict = next((v for v in specialist_verdicts if "Security" in v.agent_name), None)
        perf_verdict = next((v for v in specialist_verdicts if "Performance" in v.agent_name), None)
        test_verdict = next((v for v in specialist_verdicts if "Test" in v.agent_name), None)

        sec_score = sec_verdict.score if sec_verdict else 100
        perf_score = perf_verdict.score if perf_verdict else 100
        test_score = test_verdict.score if test_verdict else 80

        health_score = int((sec_score * 0.45) + (perf_score * 0.30) + (test_score * 0.25))

        # Check blocking conditions
        has_critical = any(i.severity == "CRITICAL" for i in all_issues)
        has_high = any(i.severity == "HIGH" for i in all_issues)

        if has_critical or sec_score < 50:
            verdict = "BLOCKED"
            executive_summary = (
                f"🛑 **MERGE BLOCKED**: The Lead Architect Council has halted merging due to critical security risks. "
                f"Hardcoded credentials or high-severity vulnerabilities were identified. "
                f"Remediate all flagged issues before requesting re-review."
            )
        elif has_high or health_score < 75:
            verdict = "CHANGES_REQUESTED"
            executive_summary = (
                f"⚠️ **CHANGES REQUESTED**: The Pull Request introduces valuable changes (+{triage.total_additions}/-{triage.total_deletions} lines), "
                f"but requires remediation of flagged security or performance anti-patterns before merging. Overall Health Score: {health_score}/100."
            )
        else:
            verdict = "APPROVED"
            executive_summary = (
                f"✅ **MERGE APPROVED**: The Pull Request passes all council quality, security, and performance standards. "
                f"Architecture is clean with a Health Score of {health_score}/100. Ready for maintainer merge."
            )

        # Recommendations list
        recommendations = []
        if has_critical:
            recommendations.append("Rotate and revoke any secrets committed in revision history.")
            recommendations.append("Apply the generated remediation patch (`git apply remediation.patch`).")
        if has_high:
            recommendations.append("Replace dynamic SQL queries or subprocess commands with parameterized APIs.")
        recommendations.append("Run the synthesized test suite to verify no regressions.")
        recommendations.append("Ensure staging environment deployment validation passes.")

        return verdict, health_score, executive_summary, recommendations
