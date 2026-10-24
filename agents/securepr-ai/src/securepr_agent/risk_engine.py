"""Contextual Risk Engine for SecurePR Agent."""
from securepr_agent.models import ExposureContext, Finding, FindingCategory, RiskScore, Severity


class RiskEngine:
    def __init__(self):
        self.category_weights = {
            FindingCategory.SECRET: {"impact": 0.95, "likelihood": 0.85},
            FindingCategory.JWT_AUTH: {"impact": 0.90, "likelihood": 0.80},
            FindingCategory.API_AUTHORIZATION: {"impact": 0.85, "likelihood": 0.75},
            FindingCategory.INPUT_VALIDATION: {"impact": 0.70, "likelihood": 0.70},
            FindingCategory.CONFIG: {"impact": 0.65, "likelihood": 0.60},
            FindingCategory.DEPENDENCY: {"impact": 0.60, "likelihood": 0.50},
        }

    def evaluate_risk(self, finding: Finding, exposure: ExposureContext) -> RiskScore:
        base = self.category_weights.get(finding.category, {"impact": 0.5, "likelihood": 0.5})
        impact = base["impact"]
        likelihood = base["likelihood"]

        exposure_multiplier = {
            ExposureContext.PUBLIC: 1.0,
            ExposureContext.AUTHENTICATED: 0.85,
            ExposureContext.INTERNAL: 0.65,
            ExposureContext.LOCAL_ONLY: 0.30,
            ExposureContext.UNKNOWN: 0.75,
        }[exposure]

        confidence = 0.90 if finding.is_new_in_diff else 0.70
        raw_composite = ((impact * 0.55) + (likelihood * 0.45)) * 10.0 * exposure_multiplier
        final_score = round(min(max(raw_composite, 0.0), 10.0), 1)

        if final_score >= 8.5:
            priority = Severity.CRITICAL
        elif final_score >= 6.5:
            priority = Severity.HIGH
        elif final_score >= 4.0:
            priority = Severity.MEDIUM
        elif final_score >= 2.0:
            priority = Severity.LOW
        else:
            priority = Severity.INFO

        rationale = (
            f"Evaluated as {priority.value} risk (Score {final_score}/10). "
            f"Asset exposure is {exposure.value} (Factor: {exposure_multiplier}). "
            f"Confidence baseline: {int(confidence * 100)}%."
        )

        return RiskScore(
            numeric_score=final_score,
            priority_level=priority,
            likelihood=likelihood,
            impact=impact,
            exposure_modifier=exposure_multiplier,
            confidence=confidence,
            rationale=rationale,
        )
