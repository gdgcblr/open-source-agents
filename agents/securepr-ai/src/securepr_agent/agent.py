"""Conversational security agent with tool-calling capabilities."""
import os
from typing import Any, Dict, List, Optional
from securepr_agent.git_diff import DiffAnalyzer
from securepr_agent.models import (
    Evidence,
    ExposureContext,
    Finding,
    FindingCategory,
    PrioritizedFinding,
    ScanReport,
    STRIDECategory,
    Severity,
)
from securepr_agent.redaction import Redactor
from securepr_agent.reporters.markdown import render_markdown_report
from securepr_agent.risk_engine import RiskEngine
from securepr_agent.threat_model import ThreatCorrelationEngine

try:
    from google import genai
except ImportError:
    genai = None


class SecurePRAgent:
    def __init__(
        self,
        files: Optional[List[Dict[str, str]]] = None,
        exposure: ExposureContext = ExposureContext.PUBLIC,
        fail_on: Severity = Severity.HIGH,
    ):
        self.files = files or []
        self.exposure = exposure
        self.fail_on = fail_on
        self.redactor = Redactor()
        self.risk_engine = RiskEngine()
        self.threat_correlator = ThreatCorrelationEngine()
        self.history: List[Dict[str, str]] = []
        self.latest_report: Optional[ScanReport] = None

    def scan(self) -> ScanReport:
        """Executes deterministic inspection across files."""
        findings: List[Finding] = []

        for f in self.files:
            file_path = f.get("path", "file.py")
            content = f.get("content", "")
            lines = content.splitlines()

            for line_idx, raw_line in enumerate(lines, start=1):
                clean_line, count = self.redactor.redact_text(raw_line)

                # 1. JWT verification disabled
                if "jwt.decode" in raw_line and ("verify=False" in raw_line or "verify_signature': False" in raw_line or '"verify_signature": False' in raw_line or 'algorithms=["none"]' in raw_line):
                    findings.append(Finding(
                        id="SEC-JWT-001",
                        title="JWT Signature Verification Explicitly Disabled",
                        category=FindingCategory.JWT_AUTH,
                        stride=[STRIDECategory.TAMPERING, STRIDECategory.SPOOFING],
                        description="jwt.decode() invoked with verify=False or algorithm 'none', allowing arbitrary claim forging without valid key signature.",
                        scanner_name="Semgrep-JWT-Rule",
                        raw_severity=Severity.CRITICAL,
                        evidence=[Evidence(file_path=file_path, start_line=line_idx, end_line=line_idx, snippet=clean_line.strip())],
                        is_new_in_diff=True,
                        cwe_id="CWE-345",
                        owasp_api_category="API2:2023 Broken Authentication",
                        remediation_hint="Enforce cryptographic signature validation by specifying the trusted public key/secret and explicit algorithm (e.g. RS256).",
                    ))

                # 2. Hardcoded Secrets
                if count > 0 and any(k in raw_line.lower() for k in ["api_key", "secret", "password", "token", "sk_live", "akia"]):
                    findings.append(Finding(
                        id=f"SEC-CRED-00{len(findings)+1}",
                        title="Hardcoded Credential or API Token Detected",
                        category=FindingCategory.SECRET,
                        stride=[STRIDECategory.INFORMATION_DISCLOSURE],
                        description=f"High-entropy private credential committed in {file_path}. Allows unauthorized external access.",
                        scanner_name="NativeSecretDetector",
                        raw_severity=Severity.CRITICAL,
                        evidence=[Evidence(file_path=file_path, start_line=line_idx, end_line=line_idx, snippet=clean_line.strip())],
                        is_new_in_diff=True,
                        cwe_id="CWE-798",
                        owasp_api_category="API7:2023 Security Misconfiguration",
                        remediation_hint="Remove hardcoded secret, rotate compromised key immediately, and inject via environment variables.",
                    ))

                # 3. BOLA / Unprotected State Mutation
                if ("@app.post" in raw_line or "@router.post" in raw_line or "@app.put" in raw_line) and "Depends(" not in raw_line:
                    findings.append(Finding(
                        id="SEC-API-002",
                        title="State Mutation Route Missing Authorization Guard (BOLA)",
                        category=FindingCategory.API_AUTHORIZATION,
                        stride=[STRIDECategory.ELEVATION_OF_PRIVILEGE],
                        description="State-altering REST endpoint defined without explicit authentication or tenant authorization guard.",
                        scanner_name="Semgrep-BOLA-Rule",
                        raw_severity=Severity.HIGH,
                        evidence=[Evidence(file_path=file_path, start_line=line_idx, end_line=min(line_idx + 3, len(lines)), snippet=clean_line.strip())],
                        is_new_in_diff=True,
                        cwe_id="CWE-285",
                        owasp_api_category="API1:2023 Broken Object Level Authorization",
                        remediation_hint="Inject authentication dependency (e.g. Depends(get_current_user)) and verify user ownership of target resource.",
                    ))

                # 4. CORS Wildcard with credentials
                if "allow_origins=[\"*\"]" in raw_line and "allow_credentials=True" in raw_line:
                    findings.append(Finding(
                        id="SEC-CFG-003",
                        title="Permissive CORS Origin with Credentials",
                        category=FindingCategory.CONFIG,
                        stride=[STRIDECategory.INFORMATION_DISCLOSURE, STRIDECategory.TAMPERING],
                        description="Wildcard CORS origin (*) is configured alongside allow_credentials=True, allowing unauthorized origins to read authenticated responses.",
                        scanner_name="ConfigAudit",
                        raw_severity=Severity.HIGH,
                        evidence=[Evidence(file_path=file_path, start_line=line_idx, end_line=line_idx, snippet=clean_line.strip())],
                        is_new_in_diff=True,
                        cwe_id="CWE-942",
                        owasp_api_category="API7:2023 Security Misconfiguration",
                        remediation_hint="Specify exact trusted frontend domains in allow_origins instead of wildcard '*'.",
                    ))

        # Threat Correlation
        hypotheses = self.threat_correlator.correlate(findings)

        # Contextual Risk Prioritization
        prioritized: List[PrioritizedFinding] = []
        severity_hierarchy = {Severity.INFO: 0, Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3, Severity.CRITICAL: 4}
        threshold_val = severity_hierarchy.get(self.fail_on, 3)
        violates_gate = False

        for f in findings:
            risk = self.risk_engine.evaluate_risk(f, self.exposure)
            if severity_hierarchy.get(risk.priority_level, 0) >= threshold_val and f.is_new_in_diff:
                violates_gate = True

            prioritized.append(PrioritizedFinding(
                finding=f,
                risk=risk,
                ai_explanation=None,
                ai_suggested_fix=f.remediation_hint,
            ))

        self.latest_report = ScanReport(
            repository_name="reviewed-repo",
            target_commit_or_branch="HEAD",
            timestamp="2026-10-24T00:00:00Z",
            total_findings=len(prioritized),
            prioritized_findings=prioritized,
            attack_path_hypotheses=hypotheses,
            redacted_item_count=self.redactor.redaction_counter,
            passed_gate=not violates_gate,
            summary={"fail_on": self.fail_on.value, "gate": "PASS" if not violates_gate else "FAIL"},
        )
        return self.latest_report

    def verify_fix(self, finding_id: str, fixed_snippet: str, target_file: str) -> Dict[str, Any]:
        """Tests whether a proposed fix resolves the specified finding."""
        # Replace file content with fixed content in a sandbox test
        test_files = []
        for f in self.files:
            if f.get("path") == target_file:
                test_files.append({"path": target_file, "content": fixed_snippet})
            else:
                test_files.append(f)

        if not any(f.get("path") == target_file for f in test_files):
            test_files.append({"path": target_file, "content": fixed_snippet})

        temp_agent = SecurePRAgent(files=test_files, exposure=self.exposure, fail_on=self.fail_on)
        report = temp_agent.scan()

        is_resolved = not any(p.finding.id == finding_id for p in report.prioritized_findings)

        if is_resolved and self.latest_report:
            for p in self.latest_report.prioritized_findings:
                if p.finding.id == finding_id:
                    p.resolved = True

        return {
            "resolved": is_resolved,
            "message": f"Fix verified for {finding_id}. Vulnerability closed." if is_resolved else f"Vulnerability {finding_id} still present.",
            "remaining_findings": [p.finding.id for p in report.prioritized_findings],
        }

    def chat_turn(self, user_message: str) -> str:
        """Handles a multi-turn conversation step using Gemini 3.8 Flash."""
        if not self.latest_report:
            self.scan()

        # Build clean sanitized context
        report_summary = f"Total findings: {self.latest_report.total_findings}, Gate: {'PASSED' if self.latest_report.passed_gate else 'BLOCKED'}\n"
        for p in self.latest_report.prioritized_findings:
            status = "[RESOLVED]" if p.resolved else f"[{p.risk.priorityLevel} - {p.risk.numericScore}/10]"
            report_summary += f"- {status} {p.finding.id}: {p.finding.title} ({p.finding.evidence[0].file_path})\n"

        prompt = f"""You are the SecurePR AI Review Agent. You assist developers in reviewing pull requests, understanding STRIDE attack paths, and verifying code fixes.
Zero-secret guarantee: All credentials have been scrubbed with safe placeholders.

Current PR Findings:
{report_summary}

Developer asks: "{user_message}"

Respond concisely and technically as a senior AppSec engineer. If proposing code fixes, provide the unified patch or exact Python/TypeScript code block."""

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key or not genai:
            return (
                f"[SecurePR Offline Mode] Regarding your query: '{user_message}'\n\n"
                f"Status: {report_summary}\n"
                f"Recommendation: Review findings marked CRITICAL/HIGH. Run `verify_fix` with secure implementations to clear the PR gate."
            )

        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
            )
            return response.text or "Analysis completed."
        except Exception as e:
            return f"Agent reasoning error: {str(e)}"
