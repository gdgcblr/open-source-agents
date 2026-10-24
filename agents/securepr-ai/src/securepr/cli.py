"""Command Line Interface for SecurePR AI."""
import json
import os
import sys
from datetime import datetime
from typing import List, Optional
import typer
from rich.console import Console

from securepr.git_diff import DiffAnalyzer
from securepr.models import (
    Evidence,
    ExposureContext,
    Finding,
    FindingCategory,
    PrioritizedFinding,
    ScanReport,
    STRIDECategory,
    Severity,
)
from securepr.redaction import Redactor
from securepr.reporters.markdown import render_markdown_report
from securepr.risk_engine import RiskEngine
from securepr.threat_model import ThreatCorrelationEngine

app = typer.Typer(help="SecurePR AI: Deterministic, PR-aware security reviewer.")
console = Console()


@app.command()
def scan(
    path: str = typer.Option(".", "--path", "-p", help="Root repository directory"),
    base_ref: str = typer.Option("origin/main", "--base", "-b", help="Base git ref for diff isolation"),
    fail_on: str = typer.Option("HIGH", "--fail-on", help="Minimum severity to return non-zero exit code (CRITICAL, HIGH, MEDIUM)"),
    markdown_out: Optional[str] = typer.Option(None, "--md-out", help="Path to write Markdown summary"),
    json_out: Optional[str] = typer.Option(None, "--json-out", help="Path to write JSON report"),
    offline: bool = typer.Option(True, "--offline/--ai-enrich", help="Run strictly offline or allow LLM summary"),
):
    """Scan changed code for security risks, correlate threat chains, and output findings."""
    console.print(f"[bold blue]SecurePR AI[/bold blue] scanning: [green]{path}[/green]")

    redactor = Redactor()
    diff_analyzer = DiffAnalyzer(repo_path=path)

    # 1. Collect Diff Lines
    try:
        diff_map = diff_analyzer.get_diff_lines(base_ref=base_ref)
        console.print(f"Diff processed: [yellow]{len(diff_map)}[/yellow] modified files tracked.")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not compute git diff ({e}). Scanning full workspace.[/yellow]")
        diff_map = {}

    findings: List[Finding] = []

    # 2. Scanning files in path
    for root, _, files in os.walk(path):
        for file in files:
            if file.endswith((".py", ".env", ".json", ".ts", ".js", ".yml", ".yaml")):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, path)

                # Skip hidden directories like .git
                if "/." in full_path or "\\." in full_path:
                    continue

                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                except Exception:
                    continue

                for line_idx, line_content in enumerate(lines, start=1):
                    is_in_diff = diff_analyzer.is_line_in_diff(rel_path, line_idx, diff_map) if diff_map else True

                    # 1. JWT verification disabled
                    if "jwt.decode" in line_content and ("verify=False" in line_content or "verify_signature': False" in line_content or "'verify_signature': False" in line_content or '"verify_signature": False' in line_content):
                        clean_code = redactor.scrub_snippet(line_content.strip())
                        findings.append(Finding(
                            id="SEC-JWT-001",
                            title="JWT Decoded with Verification Explicitly Disabled",
                            category=FindingCategory.JWT_AUTH,
                            stride=[STRIDECategory.TAMPERING, STRIDECategory.SPOOFING],
                            description="A JSON Web Token is being processed without cryptographic signature validation, allowing unauthorized claim forging.",
                            scanner_name="AST-JWT-Rule",
                            raw_severity=Severity.CRITICAL,
                            evidence=[Evidence(file_path=rel_path, start_line=line_idx, end_line=line_idx, snippet=clean_code)],
                            is_new_in_diff=is_in_diff,
                            cwe_id="CWE-345",
                            owasp_api_category="API2:2023 Broken Authentication",
                            remediation_hint="Enforce signature validation by specifying valid algorithms and verifying secret key.",
                        ))

                    # 2. Hardcoded Secrets
                    redacted_snippet, count = redactor.redact_text(line_content)
                    if count > 0 and ("api_key" in line_content.lower() or "secret" in line_content.lower() or "token" in line_content.lower() or "akia" in line_content.lower()):
                        findings.append(Finding(
                            id=f"SEC-SEC-00{len(findings)+1}",
                            title="Hardcoded Credential or API Token Detected",
                            category=FindingCategory.SECRET,
                            stride=[STRIDECategory.INFORMATION_DISCLOSURE],
                            description="High-entropy private credential committed in source file. Exposed secrets can be abused to access services.",
                            scanner_name="NativeSecretDetector",
                            raw_severity=Severity.CRITICAL,
                            evidence=[Evidence(file_path=rel_path, start_line=line_idx, end_line=line_idx, snippet=redacted_snippet.strip())],
                            is_new_in_diff=is_in_diff,
                            cwe_id="CWE-798",
                            owasp_api_category="API7:2023 Security Misconfiguration",
                            remediation_hint="Remove hardcoded secret, rotate the compromised key immediately, and inject via environment variables.",
                        ))

                    # 3. Unauthenticated state-mutation query (BOLA marker)
                    if ("@app.post" in line_content or "@router.post" in line_content or "@app.put" in line_content) and "Depends(" not in line_content:
                        clean_code = redactor.scrub_snippet(line_content.strip())
                        findings.append(Finding(
                            id="SEC-API-002",
                            title="Unprotected State Mutation Route (BOLA Risk)",
                            category=FindingCategory.API_AUTHORIZATION,
                            stride=[STRIDECategory.ELEVATION_OF_PRIVILEGE],
                            description="State-altering REST endpoint defined without explicit authentication or tenant authorization guard.",
                            scanner_name="AST-API-Rule",
                            raw_severity=Severity.HIGH,
                            evidence=[Evidence(file_path=rel_path, start_line=line_idx, end_line=line_idx, snippet=clean_code)],
                            is_new_in_diff=is_in_diff,
                            cwe_id="CWE-285",
                            owasp_api_category="API1:2023 Broken Object Level Authorization",
                            remediation_hint="Inject authentication dependency (e.g. Depends(get_current_user)) and verify user ownership of target resource.",
                        ))

                    # 4. CORS Wildcard with credentials
                    if "allow_origins=[\"*\"]" in line_content and "allow_credentials=True" in line_content:
                        clean_code = redactor.scrub_snippet(line_content.strip())
                        findings.append(Finding(
                            id="SEC-CFG-003",
                            title="Permissive CORS Origin with Credentials",
                            category=FindingCategory.CONFIG,
                            stride=[STRIDECategory.INFORMATION_DISCLOSURE, STRIDECategory.TAMPERING],
                            description="Wildcard CORS origin (*) is configured alongside allow_credentials=True, allowing unauthorized origins to read sensitive authenticated responses.",
                            scanner_name="ConfigAudit",
                            raw_severity=Severity.HIGH,
                            evidence=[Evidence(file_path=rel_path, start_line=line_idx, end_line=line_idx, snippet=clean_code)],
                            is_new_in_diff=is_in_diff,
                            cwe_id="CWE-942",
                            owasp_api_category="API7:2023 Security Misconfiguration",
                            remediation_hint="Specify exact trusted frontend domains in allow_origins instead of wildcard '*'.",
                        ))

    # 3. Threat Model & Correlation
    correlator = ThreatCorrelationEngine()
    hypotheses = correlator.correlate(findings)

    # 4. Contextual Risk Prioritization
    risk_engine = RiskEngine()
    prioritized: List[PrioritizedFinding] = []

    threshold_fail = False
    severity_order = {Severity.INFO: 0, Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3, Severity.CRITICAL: 4}
    fail_threshold_val = severity_order.get(Severity(fail_on.upper()), 3)

    for f in findings:
        exposure = ExposureContext.PUBLIC if "api" in f.evidence[0].file_path.lower() else ExposureContext.AUTHENTICATED
        calculated_risk = risk_engine.evaluate_risk(f, exposure)

        if severity_order.get(calculated_risk.priority_level, 0) >= fail_threshold_val and f.is_new_in_diff:
            threshold_fail = True

        prioritized.append(PrioritizedFinding(
            finding=f,
            risk=calculated_risk,
            ai_explanation="Deterministic static evidence points to vulnerable code path in changed diff." if offline else None,
            ai_suggested_fix=f.remediation_hint,
        ))

    passed_gate = not threshold_fail

    # 5. Assemble Scan Report
    report = ScanReport(
        repository_name=os.path.basename(os.path.abspath(path)),
        target_commit_or_branch="HEAD",
        base_commit_or_branch=base_ref,
        timestamp=datetime.utcnow().isoformat(),
        total_findings=len(prioritized),
        prioritized_findings=prioritized,
        attack_path_hypotheses=hypotheses,
        redacted_item_count=redactor.redaction_counter,
        passed_gate=passed_gate,
        summary={"fail_on_policy": fail_on, "gate_status": "PASS" if passed_gate else "FAIL"}
    )

    # 6. Outputs
    if json_out:
        with open(json_out, "w") as jf:
            jf.write(report.model_dump_json(indent=2))
        console.print(f"[green]JSON report written to: {json_out}[/green]")

    markdown_content = render_markdown_report(report)
    if markdown_out:
        with open(markdown_out, "w") as mf:
            mf.write(markdown_content)
        console.print(f"[green]Markdown report written to: {markdown_out}[/green]")

    console.print("\n--- [bold]SecurePR AI Scan Summary[/bold] ---")
    console.print(f"Total Findings: [bold]{len(prioritized)}[/bold]")
    console.print(f"Attack Path Hypotheses Formulated: [bold]{len(hypotheses)}[/bold]")
    console.print(f"Sanitized Secret Instances: [bold]{redactor.redaction_counter}[/bold]")

    if not passed_gate:
        console.print(f"[bold red]Pull Request Blocked:[/bold red] Findings violate threshold: `{fail_on}`.")
        sys.exit(1)
    else:
        console.print("[bold green]Pull Request Gate Passed.[/bold green]")
        sys.exit(0)


if __name__ == "__main__":
    app()
