"""Markdown impact report and risk assessment generator."""

from typing import List, Dict, Any
from .models import ImpactReport, RiskEvaluation, JavaMethod, CallerReference, TestRecommendation


class ImpactReporter:
    """Calculates risk and renders GitHub-flavored Markdown reports."""

    @staticmethod
    def evaluate_risk(report: ImpactReport) -> RiskEvaluation:
        """Evaluates blast radius risk tier based on caller depth, exposure, and test coverage."""
        score = 10
        factors = []

        # Factor 1: Number of changed methods
        num_methods = len(report.changed_methods)
        if num_methods == 0:
            return RiskEvaluation(tier="LOW", score=0, factors=["No Java method modifications detected in diff."])
        elif num_methods > 3:
            score += 25
            factors.append(f"Multiple methods modified ({num_methods} methods).")
        else:
            score += 10 * num_methods
            factors.append(f"{num_methods} method(s) modified.")

        # Factor 2: Direct production callers
        prod_callers = [c for c in report.callers if not c.is_test]
        if len(prod_callers) > 3:
            score += 35
            factors.append(f"Broad call graph impact: {len(prod_callers)} production callers across repository.")
        elif len(prod_callers) > 0:
            score += 20
            factors.append(f"{len(prod_callers)} direct production caller(s) identified.")
        else:
            factors.append("No external production callers discovered (isolated or entrypoint method).")

        # Factor 3: Test coverage gaps
        if report.uncovered_methods:
            score += 30
            uncovered_names = ", ".join([f"`{m.method_name}`" for m in report.uncovered_methods])
            factors.append(f"Test coverage gap: No discoverable tests for changed method(s): {uncovered_names}.")
        else:
            score -= 10
            factors.append("All changed methods have discoverable direct or indirect test references.")

        score = max(5, min(100, score))

        if score >= 70:
            tier = "CRITICAL" if score >= 85 else "HIGH"
        elif score >= 40:
            tier = "MEDIUM"
        else:
            tier = "LOW"

        return RiskEvaluation(tier=tier, score=score, factors=factors)

    @staticmethod
    def to_markdown(report: ImpactReport) -> str:
        """Renders an ImpactReport into a clean, GitHub-flavored Markdown document."""
        risk = report.risk or ImpactReporter.evaluate_risk(report)
        tier_badges = {
            "CRITICAL": "🔴 **CRITICAL RISK**",
            "HIGH": "🟠 **HIGH RISK**",
            "MEDIUM": "🟡 **MEDIUM RISK**",
            "LOW": "🟢 **LOW RISK**"
        }
        badge = tier_badges.get(risk.tier, risk.tier)

        lines: List[str] = []
        lines.append("# 💥 BlastRadius: Change Impact Analysis Report\n")
        lines.append(f"> Automated change impact assessment for target repository: `{report.target_repo}`\n")
        lines.append("## Executive Summary\n")
        lines.append(f"- **Overall Risk Rating**: {badge} (Score: `{risk.score}/100`)")
        lines.append(f"- **Changed Java Methods**: `{len(report.changed_methods)}`")
        lines.append(f"- **Discovered Direct Callers**: `{len(report.callers)}` ({len([c for c in report.callers if not c.is_test])} production, {len([c for c in report.callers if c.is_test])} tests)")
        lines.append(f"- **Recommended Tests to Run**: `{len(report.recommended_tests)}`")
        lines.append(f"- **Test Coverage Gaps**: `{len(report.uncovered_methods)}` uncovered method(s)\n")

        # Risk Factors
        lines.append("### Risk Rationale")
        for factor in risk.factors:
            lines.append(f"- {factor}")
        lines.append("")

        # Summary Notes (if any from LLM/agent)
        if report.summary_notes:
            lines.append("### Semantic Insights")
            for note in report.summary_notes:
                lines.append(f"- {note}")
            lines.append("")

        # Changed Methods Table
        lines.append("## 🔍 Changed Methods & Direct Impact\n")
        if not report.changed_methods:
            lines.append("*No Java methods directly modified in this diff.*")
        else:
            lines.append("| Modified Class | Method Signature | Lines | Return Type | Modifiers |")
            lines.append("| :--- | :--- | :--- | :--- | :--- |")
            for m in report.changed_methods:
                mods = " ".join(m.modifiers) if m.modifiers else "package-private"
                lines.append(f"| `{m.class_name}` | `{m.signature}` | `L{m.start_line}-L{m.end_line}` | `{m.return_type}` | `{mods}` |")
        lines.append("")

        # Discovered Direct Callers
        lines.append("## 🌐 Discovered Direct Callers\n")
        if not report.callers:
            lines.append("*No direct callers found in the target repository.*")
        else:
            lines.append("| Target Method | Caller Location | Type | Invocations Code Snippet |")
            lines.append("| :--- | :--- | :--- | :--- |")
            for c in report.callers:
                caller_type = "🧪 Test" if c.is_test else "⚙️ Production"
                loc = f"`{c.caller_file}#L{c.call_line}` (`{c.caller_class}#{c.caller_method}`)"
                snippet = f"`{c.code_snippet[:60]}...`" if len(c.code_snippet) > 60 else f"`{c.code_snippet}`"
                lines.append(f"| `{c.target_method_name}` | {loc} | {caller_type} | {snippet} |")
        lines.append("")

        # Recommended Tests
        lines.append("## 🧪 Recommended Test Execution Plan\n")
        if not report.recommended_tests:
            lines.append("> ⚠️ **Warning**: No existing unit or integration tests were detected for the modified code.")
        else:
            lines.append("Execute these test targets to validate your changes before deployment:\n")
            lines.append("| Priority | Test Target | Enclosing Test Method | Rationale |")
            lines.append("| :--- | :--- | :--- | :--- |")
            for t in report.recommended_tests:
                method_str = f"`{t.test_method}`" if t.test_method else "*(Full Class)*"
                priority_badge = "🔴 High" if t.priority == "HIGH" else ("🟡 Medium" if t.priority == "MEDIUM" else "🟢 Low")
                lines.append(f"| {priority_badge} | `{t.test_file}` | {method_str} | {t.reason} |")

            lines.append("\n### Suggested Maven Test Command")
            test_targets = set()
            for t in report.recommended_tests:
                if t.test_class:
                    if t.test_method:
                        test_targets.add(f"{t.test_class}#{t.test_method}")
                    else:
                        test_targets.add(f"{t.test_class}")
            cmd_targets = ",".join(sorted(test_targets))
            lines.append("```bash")
            lines.append(f"mvn test -Dtest={cmd_targets}")
            lines.append("```")
        lines.append("")

        # Coverage Gaps / Warnings
        if report.uncovered_methods:
            lines.append("## ⚠️ Test Coverage Gaps\n")
            lines.append("The following modified methods currently lack direct or discoverable caller test coverage:\n")
            for m in report.uncovered_methods:
                lines.append(f"- **`{m.fq_name}`** (`{m.file_path}:L{m.start_line}-L{m.end_line}`)")
            lines.append("\n*Recommendation: Add unit tests explicitly exercising the new or updated logic in these methods.*")
            lines.append("")

        # Limitations & Analysis Boundaries
        lines.append("## ⚠️ Limitations & Analysis Boundaries\n")
        lines.append("To maintain technical honesty and predictable scope, note the following static analysis boundaries:")
        for lim in report.limitations:
            lines.append(f"- {lim}")
        lines.append("")

        return "\n".join(lines)

