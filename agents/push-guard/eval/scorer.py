from models import Finding, Severity, ComplianceSummary, EvalScore


_SEVERITY_WEIGHT = {"CRITICAL": 40, "HIGH": 20, "MEDIUM": 8, "LOW": 2}


def calculate_risk_score(findings: list[Finding]) -> int:
    """0-100 risk score weighted by severity and confidence."""
    if not findings:
        return 0
    raw = sum(
        _SEVERITY_WEIGHT.get(f.severity.value, 0) * f.confidence
        for f in findings
    )
    return min(100, int(raw))


def evaluate_findings(findings: list[Finding]) -> EvalScore:
    """
    Self-evaluation of scan quality.
    Precision proxy: average confidence of flagged findings.
    Recall estimate: based on coverage across agent types.
    """
    if not findings:
        return EvalScore(
            precision=1.0,
            recall_estimate=0.5,
            overall=0.5,
            notes="No findings — either clean diff or agents missed issues.",
        )

    agents_fired = {f.agent for f in findings}
    precision = sum(f.confidence for f in findings) / len(findings)

    # Recall estimate: reward for multi-agent coverage
    coverage_score = len(agents_fired) / 3.0
    recall_estimate = round(0.4 + (0.5 * coverage_score), 2)

    overall = round((precision + recall_estimate) / 2, 2)

    notes = (
        f"{len(findings)} finding(s) across {len(agents_fired)} agent(s). "
        f"Agents fired: {', '.join(sorted(agents_fired))}."
    )

    return EvalScore(
        precision=round(precision, 2),
        recall_estimate=recall_estimate,
        overall=overall,
        notes=notes,
    )


def generate_compliance(findings: list[Finding]) -> ComplianceSummary:
    severities = {f.severity.value for f in findings}
    has_critical = "CRITICAL" in severities
    has_high = "HIGH" in severities

    agents = {f.agent for f in findings}
    has_injection = "PromptInjectionAgent" in agents
    has_secrets = "SecretsAgent" in agents

    if has_critical or has_high:
        eu_cra = "FAIL — Critical/High vulnerabilities violate EU Cyber Resilience Act Article 13 (security by design)"
        nist_ssdf = "FAIL — Violates NIST SSDF PW.8.1: review code for security issues before release"
    elif findings:
        eu_cra = "WARN — Medium findings require remediation before production release"
        nist_ssdf = "WARN — Address findings per NIST SSDF RV.1.1"
    else:
        eu_cra = "PASS — No security issues detected"
        nist_ssdf = "PASS — Compliant with NIST SSDF PW.8.1"

    if has_injection:
        owasp_llm = "FAIL — OWASP LLM01:2025 Prompt Injection detected in committed code"
    elif has_secrets:
        owasp_llm = "WARN — Hardcoded credentials risk LLM API abuse (OWASP LLM02:2025)"
    else:
        owasp_llm = "PASS — No OWASP LLM Top 10 violations detected"

    return ComplianceSummary(eu_cra=eu_cra, nist_ssdf=nist_ssdf, owasp_llm=owasp_llm)


def build_summary(findings: list[Finding], risk_score: int) -> str:
    if not findings:
        return "No security issues detected. This diff appears safe to push."
    counts = {}
    for f in findings:
        counts[f.severity.value] = counts.get(f.severity.value, 0) + 1
    parts = [f"{v} {k}" for k, v in counts.items()]
    return (
        f"PushGuard blocked this push with risk score {risk_score}/100. "
        f"Found: {', '.join(parts)}. Resolve all CRITICAL and HIGH findings before pushing."
    )
