"""Multi-Service Change Impact Orchestrator.

Coordinates cross-service impact analysis when a Pull Request is raised on a primary microservice,
querying registered neighbouring service agents to detect breaking downstream dependencies and test risks.
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

from .agent import BlastRadiusAgent
from .java_analyzer import JavaAnalyzer
from .test_recommender import TestRecommender
from .models import JavaMethod, CallerReference, TestRecommendation, RiskEvaluation, ImpactReport
from .reporter import ImpactReporter


@dataclass
class ServiceImpact:
    """Impact assessment for a specific microservice."""
    service_name: str
    is_impacted: bool
    is_target_service: bool = False
    direct_callers: List[CallerReference] = field(default_factory=list)
    recommended_tests: List[TestRecommendation] = field(default_factory=list)
    risk_tier: str = "NONE"
    rationale: List[str] = field(default_factory=list)


@dataclass
class MultiServiceReport:
    """Comprehensive cross-microservice change impact report."""
    target_service: str
    overall_risk: RiskEvaluation
    changed_methods: List[JavaMethod]
    service_impacts: Dict[str, ServiceImpact] = field(default_factory=dict)
    summary_notes: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Renders cross-service impact report in GitHub-flavored Markdown."""
        tier_badges = {
            "CRITICAL": "🔴 **CRITICAL RISK**",
            "HIGH": "🟠 **HIGH RISK**",
            "MEDIUM": "🟡 **MEDIUM RISK**",
            "LOW": "🟢 **LOW RISK**"
        }
        badge = tier_badges.get(self.overall_risk.tier, self.overall_risk.tier)

        lines: List[str] = []
        lines.append("# 🌐 Multi-Service BlastRadius: Cross-Service Change Impact Report\n")
        lines.append(f"> Pull Request impact analysis initiated on primary service: `{self.target_service}`\n")
        lines.append("## Executive Multi-Service Summary\n")
        lines.append(f"- **Global Cross-Service Risk**: {badge} (Score: `{self.overall_risk.score}/100`)")
        lines.append(f"- **Primary Modified Service**: `{self.target_service}`")

        impacted_services = [s for s, imp in self.service_impacts.items() if imp.is_impacted and not imp.is_target_service]
        unaffected_services = [s for s, imp in self.service_impacts.items() if not imp.is_impacted and not imp.is_target_service]

        lines.append(f"- **Impacted Downstream Services ({len(impacted_services)})**: {', '.join([f'`{s}`' for s in impacted_services]) if impacted_services else 'None'}")
        lines.append(f"- **Unaffected Neighbour Services ({len(unaffected_services)})**: {', '.join([f'`{s}`' for s in unaffected_services]) if unaffected_services else 'None'}\n")

        # Global Risk Rationale
        lines.append("### Risk Assessment Rationale")
        for f in self.overall_risk.factors:
            lines.append(f"- {f}")
        lines.append("")

        # Service-by-Service Breakdown Table
        lines.append("## 🏢 Microservice Ecosystem Impact Matrix\n")
        lines.append("| Microservice | Relationship | Status | Risk Level | Callers Found | Tests Impacted |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")

        for s_name, imp in self.service_impacts.items():
            rel = "🎯 Target (Modified)" if imp.is_target_service else "📡 Downstream Neighbour"
            status = "⚠️ Impacted" if imp.is_impacted else "✅ Unaffected"
            lvl = imp.risk_tier
            lines.append(f"| `{s_name}` | {rel} | {status} | **{lvl}** | `{len(imp.direct_callers)}` | `{len(imp.recommended_tests)}` |")
        lines.append("")

        # Detailed Breakdown for Impacted Services
        lines.append("## 🔍 Service Impact Details\n")
        for s_name, imp in self.service_impacts.items():
            if not imp.is_impacted:
                continue

            lines.append(f"### Service: `{s_name}` ({imp.risk_tier} Risk)\n")
            for r in imp.rationale:
                lines.append(f"- {r}")

            if imp.direct_callers:
                lines.append("\n**Discovered Invocations:**")
                for c in imp.direct_callers:
                    tag = "🧪 Test" if c.is_test else "⚙️ Production"
                    lines.append(f"- [{tag}] `{c.caller_file}#L{c.call_line}` (`{c.caller_class}#{c.caller_method}`): `{c.code_snippet}`")

            if imp.recommended_tests:
                lines.append("\n**Recommended Selective Tests to Run:**")
                for t in imp.recommended_tests:
                    method_str = f"#{t.test_method}" if t.test_method else ""
                    lines.append(f"- `{t.test_class}{method_str}`: {t.reason}")

                test_targets = {
                    f"{t.test_class}#{t.test_method}" if t.test_method else t.test_class
                    for t in imp.recommended_tests if t.test_class
                }
                lines.append(f"\n```bash\n# In {s_name} directory:\nmvn test -Dtest={','.join(sorted(test_targets))}\n```\n")

        lines.append("## ⚠️ Multi-Service Boundaries & Verification Notes\n")
        lines.append("- Service agents independently analyzed their local ASTs against the public API signatures exported by the target service.")
        lines.append("- Asynchronous event contracts (e.g. Kafka/RabbitMQ) and runtime schema registries should be validated alongside HTTP/Feign clients.")

        return "\n".join(lines)


class ServiceAgent:
    """Autonomous agent representing a single microservice."""

    def __init__(self, service_name: str, service_path: Path):
        self.service_name = service_name
        self.service_path = Path(service_path).resolve()
        self.analyzer = JavaAnalyzer(self.service_path)
        self.test_recommender = TestRecommender(self.analyzer)

    def assess_impact(self, changed_methods: List[JavaMethod]) -> ServiceImpact:
        """Checks if any changed methods from an external service impact this microservice."""
        all_callers: List[CallerReference] = []

        for m in changed_methods:
            # Check for direct calls to the modified method
            callers = self.analyzer.find_direct_callers(m.method_name, m.class_name)
            all_callers.extend(callers)

        # Deduplicate callers
        unique_callers = []
        seen = set()
        for c in all_callers:
            key = (c.caller_file, c.caller_class, c.caller_method, c.call_line)
            if key not in seen:
                seen.add(key)
                unique_callers.append(c)

        if not unique_callers:
            return ServiceImpact(
                service_name=self.service_name,
                is_impacted=False,
                is_target_service=False,
                risk_tier="NONE",
                rationale=[f"No invocations of changed methods found in `{self.service_name}`."]
            )

        # Recommend impacted tests in this service
        tests = self.test_recommender.recommend_tests(changed_methods, unique_callers)

        prod_callers = [c for c in unique_callers if not c.is_test]
        risk_tier = "HIGH" if len(prod_callers) > 0 else "MEDIUM"
        rationale = [
            f"Found {len(prod_callers)} production call site(s) and {len(unique_callers) - len(prod_callers)} test call site(s) referencing changed methods."
        ]

        return ServiceImpact(
            service_name=self.service_name,
            is_impacted=True,
            is_target_service=False,
            direct_callers=unique_callers,
            recommended_tests=tests,
            risk_tier=risk_tier,
            rationale=rationale
        )


class MultiServiceOrchestrator:
    """Orchestrator agent coordinating multi-microservice impact analysis."""

    def __init__(self):
        self.services: Dict[str, ServiceAgent] = {}

    def register_service(self, service_name: str, service_path: str):
        """Registers a microservice agent with the orchestrator."""
        self.services[service_name] = ServiceAgent(service_name, Path(service_path))

    def discover_services(self, root_dir: str):
        """Automatically registers all child directories containing Java projects."""
        p = Path(root_dir).resolve()
        for child in p.iterdir():
            if child.is_dir() and not child.name.startswith("."):
                # If child has pom.xml or src directory, register as service
                if (child / "pom.xml").exists() or (child / "src").exists():
                    self.register_service(child.name, str(child))

    def orchestrate_pr_impact(self, diff_content: str, target_service_name: str) -> MultiServiceReport:
        """Executes full cross-service impact analysis for a PR raised on target_service_name."""
        if target_service_name not in self.services:
            raise ValueError(f"Target service '{target_service_name}' is not registered with Orchestrator.")

        target_agent = self.services[target_service_name]

        # Step 1: Target service analyzes PR diff
        local_blast = BlastRadiusAgent(repo_path=str(target_agent.service_path))
        local_report = local_blast.analyze_diff(diff_content)

        service_impacts: Dict[str, ServiceImpact] = {}

        # Record target service impact
        service_impacts[target_service_name] = ServiceImpact(
            service_name=target_service_name,
            is_impacted=True,
            is_target_service=True,
            direct_callers=local_report.callers,
            recommended_tests=local_report.recommended_tests,
            risk_tier=local_report.risk.tier if local_report.risk else "MEDIUM",
            rationale=[f"Primary service where PR was raised. {len(local_report.changed_methods)} method(s) modified."]
        )

        # Step 2 & 3: Query registered neighbouring service agents
        impacted_neighbours_count = 0
        for s_name, agent in self.services.items():
            if s_name == target_service_name:
                continue

            # Query neighbour service agent
            impact = agent.assess_impact(local_report.changed_methods)
            service_impacts[s_name] = impact
            if impact.is_impacted:
                impacted_neighbours_count += 1

        # Step 4: Calculate Global Cross-Service Risk
        global_score = 30
        global_factors = []

        global_factors.append(f"PR modifies `{len(local_report.changed_methods)}` method(s) in `{target_service_name}`.")

        if impacted_neighbours_count > 0:
            global_score += 45
            impacted_names = [s for s, imp in service_impacts.items() if imp.is_impacted and not imp.is_target_service]
            global_factors.append(f"Downstream service impact detected: {len(impacted_names)} neighbouring service(s) ({', '.join(impacted_names)}) call modified methods.")
        else:
            global_factors.append("No neighbouring microservices have discoverable dependencies on the modified code (isolated change).")

        global_score = min(100, global_score)
        tier = "CRITICAL" if global_score >= 85 else ("HIGH" if global_score >= 70 else ("MEDIUM" if global_score >= 40 else "LOW"))

        overall_risk = RiskEvaluation(tier=tier, score=global_score, factors=global_factors)

        return MultiServiceReport(
            target_service=target_service_name,
            overall_risk=overall_risk,
            changed_methods=local_report.changed_methods,
            service_impacts=service_impacts,
            summary_notes=[]
        )

