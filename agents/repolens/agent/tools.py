"""
RepoLens — ADK Agent Read-Only Tools

These two tools are the ONLY mechanisms the ADK agent can use to access
scan data. They are strictly read-only and operate only on data that was
already collected and validated by the backend scanners.

Neither tool has access to the filesystem, shell, network, or database.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# The scan context is injected by agent/runner.py before tool calls.
# This avoids global state; the runner passes an immutable snapshot.

def make_tools(report_snapshot: dict[str, Any]):
    """
    Factory that returns bound tool functions for a specific scan report.

    Args:
        report_snapshot: The AuditReport serialized to a dict (already validated).

    Returns:
        (get_scan_summary, get_finding_details) — closures bound to the snapshot.
    """
    findings_index: dict[str, dict] = {
        f["finding_id"]: f
        for f in report_snapshot.get("findings", [])
    }

    def get_scan_summary() -> dict[str, Any]:
        """
        Return a summary of the security audit: repository info, scanner status,
        total findings, and severity breakdown.

        This tool does NOT return raw file content or secrets.
        """
        findings = report_snapshot.get("findings", [])
        severity_counts: dict[str, int] = {}
        for f in findings:
            sev = f.get("severity", "UNKNOWN")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        scanner_status = {
            name: {
                "available": s.get("available", False),
                "finding_count": s.get("finding_count", 0),
                "error": s.get("error_message"),
            }
            for name, s in report_snapshot.get("scanner_status", {}).items()
        }

        top_findings = [
            {
                "finding_id": f.get("finding_id"),
                "title": f.get("title"),
                "severity": f.get("severity"),
                "scanner": f.get("scanner"),
                "file_path": f.get("file_path"),
            }
            for f in findings[:25]
        ]

        return {
            "repository_name": report_snapshot.get("repository_name"),
            "commit_sha": report_snapshot.get("commit_sha"),
            "tech_stack": report_snapshot.get("tech_stack", []),
            "total_findings": len(findings),
            "severity_breakdown": severity_counts,
            "scanner_status": scanner_status,
            "is_demo": report_snapshot.get("is_demo", False),
            "top_findings": top_findings,
        }

    def get_finding_details(finding_id: str) -> dict[str, Any]:
        """
        Return details for a specific finding by its finding_id.

        Args:
            finding_id: The UUID of the finding (from get_scan_summary or the findings list).

        Returns:
            Finding details dict, or an error dict if the ID is not found.

        IMPORTANT: Only returns findings that exist in the scanner output.
        References to nonexistent IDs are rejected.
        """
        if not finding_id or not isinstance(finding_id, str):
            return {"error": "finding_id must be a non-empty string"}

        finding = findings_index.get(finding_id.strip())
        if finding is None:
            logger.warning("Agent requested unknown finding_id: %r", finding_id)
            return {
                "error": f"Finding ID {finding_id!r} not found in scan results.",
                "note": "Only IDs from the current scan are valid.",
            }

        # Return a safe subset — exclude raw evidence if it was somehow not redacted
        return {
            "finding_id": finding.get("finding_id"),
            "title": finding.get("title"),
            "severity": finding.get("severity"),
            "category": finding.get("category"),
            "scanner": finding.get("scanner"),
            "rule_id": finding.get("rule_id"),
            "file_path": finding.get("file_path"),
            "line_start": finding.get("line_start"),
            "line_end": finding.get("line_end"),
            "evidence": finding.get("evidence"),   # already redacted by normalizer
            "remediation": finding.get("remediation"),
            "source_url": finding.get("source_url"),
            "provenance": finding.get("provenance"),
        }

    return get_scan_summary, get_finding_details
