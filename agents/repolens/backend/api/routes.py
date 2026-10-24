"""
RepoLens — FastAPI Routes

Implements only the required endpoints:
  GET  /api/health
  GET  /api/audits
  GET  /api/audits/{audit_id}
  POST /api/scans
  GET  /api/audits/{audit_id}/report
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.models import (
    AuditDetail,
    AuditReport,
    AuditSummary,
    HealthResponse,
    ScanRequest,
    ScanResponse,
)
from backend.scanner.validator import ValidationError
from backend.scanner.cloner import CloneError

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db_row_to_summary(row: dict) -> AuditSummary:
    report_json = row.get("report_json") or {}
    findings = report_json.get("findings", []) if isinstance(report_json, dict) else []
    counts: dict[str, int] = {}
    for f in findings:
        sev = f.get("severity", "UNKNOWN")
        counts[sev] = counts.get(sev, 0) + 1
    return AuditSummary(
        id=row["id"],
        repository_url=row["repository_url"],
        repository_name=row["repository_name"],
        scan_status=row["scan_status"],
        is_demo=row["is_demo"],
        commit_sha=row.get("commit_sha"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        critical_count=counts.get("CRITICAL", 0),
        high_count=counts.get("HIGH", 0),
        medium_count=counts.get("MEDIUM", 0),
        low_count=counts.get("LOW", 0),
        total_findings=len(findings),
    )


def _db_row_to_detail(row: dict) -> AuditDetail:
    summary = _db_row_to_summary(row)
    return AuditDetail(
        **summary.model_dump(),
        report_json=row.get("report_json"),
        report_markdown=row.get("report_markdown"),
    )


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@router.get("/health", response_model=HealthResponse)
def health_check():
    settings = get_settings()
    db_status = "unknown"
    try:
        from backend.db import health_check as db_ping
        db_status = "ok" if db_ping() else "unreachable"
    except Exception:
        logger.exception("Health check failed while checking database")
        db_status = "unreachable"
    return HealthResponse(
        status="ok",
        database=db_status,
        gemini_configured=settings.gemini_available,
    )


# ---------------------------------------------------------------------------
# GET /audits
# ---------------------------------------------------------------------------

@router.get("/audits", response_model=list[AuditSummary])
def list_audits():
    try:
        from backend.db import list_audits as db_list
        rows = db_list(limit=20)
        return [_db_row_to_summary(r) for r in rows]
    except Exception as exc:
        logger.error("list_audits failed: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable.")


# ---------------------------------------------------------------------------
# GET /audits/{audit_id}
# ---------------------------------------------------------------------------

@router.get("/audits/{audit_id}", response_model=AuditDetail)
def get_audit(audit_id: int):
    try:
        from backend.db import get_audit_by_id
        row = get_audit_by_id(audit_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Audit not found.")
        return _db_row_to_detail(row)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_audit failed: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable.")


# ---------------------------------------------------------------------------
# POST /scans
# ---------------------------------------------------------------------------

@router.post("/scans", response_model=ScanResponse)
def start_scan(req: ScanRequest):
    """
    Synchronously validates URL, clones, runs scanners, enriches with AI,
    and persists to PostgreSQL. Returns audit_id on success.

    Resource limits are enforced. Runs synchronously (no job queue in MVP).
    """
    from backend.scanner.validator import validate_github_url
    from backend.scanner.orchestrator import run_full_scan
    from agent.runner import run_agent_sync

    # Step 1 — URL validation
    try:
        normalized_url, repo_name = validate_github_url(req.repository_url)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Step 2 — Scan
    try:
        report = run_full_scan(normalized_url)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except CloneError as exc:
        logger.warning("Could not scan %s: %s", normalized_url, exc)
        raise HTTPException(
            status_code=422,
            detail="Could not scan this repository. Confirm it is public and within the configured size and time limits.",
        ) from exc
    except Exception as exc:
        logger.exception("Scan failed for %s", normalized_url)
        raise HTTPException(status_code=500, detail="Scan failed due to an internal error.") from exc

    # Step 3 — AI enrichment (non-fatal)
    try:
        ai_summary, ai_actions = run_agent_sync(report)
        report.ai_summary = ai_summary
        report.ai_prioritized_actions = ai_actions
        report.ai_available = ai_summary is not None
    except Exception as exc:
        logger.warning("AI enrichment failed (continuing without): %s", exc)

    # Step 4 — Build markdown report
    report_markdown = _build_markdown(report)

    # Step 5 — Persist
    try:
        from backend.db import upsert_audit
        scanner_status_dict = {
            name: s.model_dump()
            for name, s in report.scanner_status.items()
        }
        audit_id = upsert_audit(
            repository_url=report.repository_url,
            repository_name=report.repository_name,
            commit_sha=report.commit_sha,
            scan_status="completed",
            is_demo=False,
            report_json=report.model_dump(mode="json"),
            report_markdown=report_markdown,
            scanner_status=scanner_status_dict,
        )
    except Exception as exc:
        logger.error("Persist failed: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable.")

    return ScanResponse(
        audit_id=audit_id,
        status="completed",
        message=f"Scan completed. {len(report.findings)} findings.",
    )


# ---------------------------------------------------------------------------
# GET /audits/{audit_id}/report
# ---------------------------------------------------------------------------

@router.get("/audits/{audit_id}/report")
def get_report(audit_id: int, format: str = "json"):
    """
    Download the report as JSON or Markdown.
    ?format=json  (default)
    ?format=markdown
    """
    try:
        from backend.db import get_audit_by_id
        row = get_audit_by_id(audit_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Audit not found.")
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_report failed for audit %s", audit_id)
        raise HTTPException(status_code=503, detail="Database unavailable.")

    if format == "markdown":
        md = row.get("report_markdown") or "No markdown report available."
        return Response(
            content=md,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="audit-{audit_id}.md"'},
        )

    return JSONResponse(
        content=row.get("report_json") or {},
        headers={"Content-Disposition": f'attachment; filename="audit-{audit_id}.json"'},
    )


# ---------------------------------------------------------------------------
# Report Markdown Builder
# ---------------------------------------------------------------------------

def _build_markdown(report: AuditReport) -> str:
    lines = [
        f"# RepoLens Security Audit: {report.repository_name}",
        "",
        f"**Repository:** {report.repository_url}",
        f"**Commit SHA:** {report.commit_sha or 'N/A'}",
        f"**Tech Stack:** {', '.join(report.tech_stack) or 'Not detected'}",
        f"**Generated:** {report.generated_at.isoformat()}",
        f"**Demo Report:** {'Yes (illustrative — not a verified scan)' if report.is_demo else 'No'}",
        "",
        "---",
        "",
        "## Scanner Status",
        "",
    ]
    for scanner, status in report.scanner_status.items():
        avail = "✅ Available" if status.available else "❌ Not available"
        err = f" — {status.error_message}" if status.error_message else ""
        lines.append(f"- **{scanner}**: {avail}{err} ({status.finding_count} findings)")

    lines += ["", "---", "", "## Findings Summary", ""]

    sev_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"]
    counts: dict[str, int] = {}
    for f in report.findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    lines.append("| Severity | Count |")
    lines.append("| --- | --- |")
    for sev in sev_order:
        if counts.get(sev, 0) > 0:
            lines.append(f"| {sev} | {counts[sev]} |")
    lines.append(f"| **Total** | **{len(report.findings)}** |")

    if report.ai_summary:
        lines += ["", "---", "", "## AI Audit Summary (Gemini)", ""]
        lines.append(report.ai_summary)
        if report.ai_prioritized_actions:
            lines += ["", "### Prioritized Actions", ""]
            for i, action in enumerate(report.ai_prioritized_actions, 1):
                lines.append(f"{i}. {action}")

    lines += ["", "---", "", "## Detailed Findings", ""]
    for f in report.findings:
        lines.append(f"### [{f.severity}] {f.title}")
        lines.append(f"- **Scanner:** {f.scanner}")
        if f.rule_id:
            lines.append(f"- **Rule/Advisory:** {f.rule_id}")
        if f.file_path:
            loc = f.file_path
            if f.line_start:
                loc += f":{f.line_start}"
            lines.append(f"- **Location:** `{loc}`")
        if f.evidence:
            lines.append(f"- **Evidence:** `{f.evidence}`")
        if f.remediation:
            lines.append(f"- **Remediation:** {f.remediation}")
        if f.provenance == "ai_suggestion":
            lines.append("- ⚠️ *[UNVERIFIED AI SUGGESTION — not confirmed by scanner]*")
        lines.append("")

    lines += [
        "---",
        "",
        "*Generated by RepoLens. Scanner findings are sourced from Trivy and Semgrep. "
        "AI summaries are generated by Gemini and should be verified independently.*",
    ]

    return "\n".join(lines)
