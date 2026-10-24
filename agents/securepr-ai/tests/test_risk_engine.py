from securepr.models import Evidence, ExposureContext, Finding, FindingCategory, STRIDECategory, Severity
from securepr.risk_engine import RiskEngine


def test_public_endpoint_yields_higher_risk():
    engine = RiskEngine()
    finding = Finding(
        id="SEC-API-001",
        title="BOLA flaw in user retrieval",
        category=FindingCategory.API_AUTHORIZATION,
        stride=[STRIDECategory.ELEVATION_OF_PRIVILEGE],
        description="Missing user identity match",
        scanner_name="AST-API",
        raw_severity=Severity.HIGH,
        evidence=[Evidence(file_path="api/routes.py", start_line=10, end_line=12, snippet="db.query()")],
        is_new_in_diff=True,
        remediation_hint="Add ownership check",
    )

    public_risk = engine.evaluate_risk(finding, ExposureContext.PUBLIC)
    internal_risk = engine.evaluate_risk(finding, ExposureContext.INTERNAL)

    assert public_risk.numeric_score > internal_risk.numeric_score
    assert public_risk.priority_level in [Severity.CRITICAL, Severity.HIGH]
