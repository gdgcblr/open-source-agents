"""
RepoLens — Finding Normalizer

Converts raw Trivy and Semgrep JSON output into the shared Finding schema.
Unknown or missing fields are handled gracefully. Failed scanners are
represented honestly — never as a clean scan.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from backend.models import Finding
from backend.scanner.redactor import redact_evidence
from backend.config import get_settings

logger = logging.getLogger(__name__)


def _make_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Severity normalisation
# ---------------------------------------------------------------------------

_SEV_MAP: dict[str, str] = {
    "critical": "CRITICAL",
    "high":     "HIGH",
    "medium":   "MEDIUM",
    "moderate": "MEDIUM",
    "low":      "LOW",
    "info":     "INFO",
    "note":     "INFO",
    "warning":  "LOW",
    "unknown":  "UNKNOWN",
    "":         "UNKNOWN",
}


def _norm_sev(raw: str) -> str:
    return _SEV_MAP.get(raw.lower().strip(), "UNKNOWN")


# ---------------------------------------------------------------------------
# Trivy normalisation
# ---------------------------------------------------------------------------

def normalize_trivy(trivy_json: dict[str, Any]) -> list[Finding]:
    """
    Parse Trivy JSON output (--format json) and return normalized Findings.
    Trivy output schema: {"Results": [{"Target": ..., "Vulnerabilities": [...], "Secrets": [...]}]}
    """
    settings = get_settings()
    findings: list[Finding] = []
    results = trivy_json.get("Results") or []

    for result in results:
        target = result.get("Target", "")
        result_type = result.get("Type", "")

        # Dependency / OS vulnerabilities
        for vuln in result.get("Vulnerabilities") or []:
            pkg = vuln.get("PkgName", "")
            installed = vuln.get("InstalledVersion", "")
            fixed = vuln.get("FixedVersion", "")
            vuln_id = vuln.get("VulnerabilityID", "")
            title = vuln.get("Title") or vuln_id or "Unknown vulnerability"
            sev = _norm_sev(vuln.get("Severity", ""))
            refs = vuln.get("References") or []
            source_url = refs[0] if refs else None
            remediation = (
                f"Upgrade {pkg} from {installed} to {fixed}."
                if fixed else
                f"No fixed version available for {pkg}@{installed}. Monitor for updates."
            )
            evidence = f"{pkg}@{installed} — {vuln_id}"
            findings.append(Finding(
                finding_id=_make_id(),
                title=title,
                severity=sev,
                category="dependency",
                scanner="trivy",
                rule_id=vuln_id,
                advisory_ref=vuln_id,
                file_path=target,
                evidence=redact_evidence(evidence, settings.max_snippet_bytes),
                remediation=remediation,
                source_url=source_url,
                provenance="scanner",
            ))

        # Secrets
        for secret in result.get("Secrets") or []:
            category_raw = secret.get("Category", "secret")
            rule_id = secret.get("RuleID", "")
            title = secret.get("Title") or rule_id or "Potential secret detected"
            match = secret.get("Match", "")
            start_line = secret.get("StartLine")
            end_line = secret.get("EndLine")
            findings.append(Finding(
                finding_id=_make_id(),
                title=title,
                severity="HIGH",
                category="secret",
                scanner="trivy",
                rule_id=rule_id,
                file_path=target,
                line_start=start_line,
                line_end=end_line,
                # Redact the match — it may contain the actual secret value
                evidence=redact_evidence(match, settings.max_snippet_bytes),
                remediation=(
                    "Remove the secret from the repository and rotate the credential. "
                    "Use environment variables or a secrets manager instead."
                ),
                provenance="scanner",
            ))

        # Misconfigurations
        for misconf in result.get("Misconfigurations") or []:
            title = misconf.get("Title") or misconf.get("ID") or "Misconfiguration"
            sev = _norm_sev(misconf.get("Severity", ""))
            description = misconf.get("Description", "")
            resolution = misconf.get("Resolution", "")
            ref_id = misconf.get("ID", "")
            findings.append(Finding(
                finding_id=_make_id(),
                title=title,
                severity=sev,
                category="misconfiguration",
                scanner="trivy",
                rule_id=ref_id,
                file_path=target,
                evidence=redact_evidence(description, settings.max_snippet_bytes),
                remediation=resolution or "Review the misconfiguration and apply recommended settings.",
                provenance="scanner",
            ))

    logger.info("Trivy: normalized %d findings from %d result sets", len(findings), len(results))
    return findings


# ---------------------------------------------------------------------------
# Semgrep normalisation
# ---------------------------------------------------------------------------

def normalize_semgrep(semgrep_json: dict[str, Any]) -> list[Finding]:
    """
    Parse Semgrep JSON output (--json) and return normalized Findings.
    Semgrep output schema: {"results": [...], "errors": [...]}
    """
    settings = get_settings()
    findings: list[Finding] = []
    results = semgrep_json.get("results") or []

    for item in results:
        rule_id = item.get("check_id", "")
        path = item.get("path", "")
        start = item.get("start") or {}
        end = item.get("end") or {}
        line_start = start.get("line")
        line_end = end.get("line")
        message = item.get("extra", {}).get("message", "") or item.get("message", "")
        sev_raw = item.get("extra", {}).get("severity", "")
        # Semgrep uses ERROR/WARNING/INFO
        _semgrep_sev_map = {"error": "HIGH", "warning": "MEDIUM", "info": "LOW"}
        sev = _semgrep_sev_map.get(sev_raw.lower(), "UNKNOWN")
        lines = item.get("extra", {}).get("lines", "")
        metadata = item.get("extra", {}).get("metadata") or {}
        source_url = metadata.get("source") or metadata.get("references", [None])[0] if isinstance(metadata.get("references"), list) else None
        cwe = metadata.get("cwe", [])
        if isinstance(cwe, list):
            cwe_str = ", ".join(cwe)
        else:
            cwe_str = str(cwe)
        title = message[:120] if message else rule_id
        remediation = metadata.get("fix", "") or metadata.get("message", "") or "Review rule documentation and apply recommended fix."
        findings.append(Finding(
            finding_id=_make_id(),
            title=title,
            severity=sev,
            category="sast",
            scanner="semgrep",
            rule_id=rule_id,
            advisory_ref=cwe_str or None,
            file_path=path,
            line_start=line_start,
            line_end=line_end,
            evidence=redact_evidence(lines, settings.max_snippet_bytes),
            remediation=remediation,
            source_url=source_url,
            provenance="scanner",
        ))

    logger.info("Semgrep: normalized %d findings", len(findings))
    return findings
