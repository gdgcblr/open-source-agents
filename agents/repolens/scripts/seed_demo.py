"""
RepoLens — Demo Seed Script

Seeds exactly one demo repository and report into PostgreSQL.
Idempotent: running multiple times does not create duplicates or
delete unrelated records. Uses ON CONFLICT DO UPDATE in the database layer.

Demo repository: https://github.com/OWASP/NodeGoat
This is a well-known intentionally vulnerable Node.js application
maintained by OWASP for educational security training.

IMPORTANT: The report below is ILLUSTRATIVE. It was not produced by an
actual Trivy or Semgrep scan of the repository. The `is_demo=True` flag
is set, and the UI clearly labels it as illustrative.
Run `scripts/seed_demo.py --real-scan` (requires Trivy + Semgrep) to
replace it with a genuine scan result.

Usage:
    cd agents/repolens
    python scripts/seed_demo.py
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from scripts/ or from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

DEMO_URL = "https://github.com/OWASP/NodeGoat"
DEMO_REPO_NAME = "OWASP/NodeGoat"
DEMO_COMMIT_SHA = None  # Not recorded — genuine scan not performed

# ---------------------------------------------------------------------------
# Illustrative demo report (is_demo=True)
# ---------------------------------------------------------------------------

DEMO_REPORT: dict = {
    "repository_url": DEMO_URL,
    "repository_name": DEMO_REPO_NAME,
    "commit_sha": DEMO_COMMIT_SHA,
    "tech_stack": ["Node.js"],
    "is_demo": True,
    "ai_available": False,
    "ai_summary": None,
    "ai_prioritized_actions": [],
    "scan_duration_seconds": None,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "scanner_status": {
        "trivy": {
            "available": False,
            "exit_code": None,
            "error_message": "Illustrative demo — no real scan performed",
            "finding_count": 0,
        },
        "semgrep": {
            "available": False,
            "exit_code": None,
            "error_message": "Illustrative demo — no real scan performed",
            "finding_count": 0,
        },
    },
    "findings": [
        {
            "finding_id": "demo-001",
            "title": "Hard-coded MongoDB connection string with credentials",
            "severity": "HIGH",
            "category": "secret",
            "scanner": "trivy",
            "rule_id": "secret-hardcoded-database-url",
            "advisory_ref": None,
            "file_path": "config/env/development.js",
            "line_start": 5,
            "line_end": 5,
            "evidence": "db: 'mongodb://[REDACTED]@localhost/nodegoat'",
            "remediation": (
                "Move database credentials to environment variables. "
                "Use process.env.DB_URL and store the actual value in .env (gitignored)."
            ),
            "source_url": None,
            "provenance": "scanner",
        },
        {
            "finding_id": "demo-002",
            "title": "SQL Injection via unsanitized user input in allocation query",
            "severity": "HIGH",
            "category": "sast",
            "scanner": "semgrep",
            "rule_id": "javascript.lang.security.audit.sqli.node-mssql-sqli",
            "advisory_ref": "CWE-89",
            "file_path": "app/data/allocations-dao.js",
            "line_start": 37,
            "line_end": 41,
            "evidence": "db.collection(\"allocations\").find({userId: Number(userId)})",
            "remediation": (
                "Use parameterized queries or an ODM that escapes inputs. "
                "Validate and cast userId before use. Consider Mongoose schema validation."
            ),
            "source_url": "https://owasp.org/www-community/attacks/SQL_Injection",
            "provenance": "scanner",
        },
        {
            "finding_id": "demo-003",
            "title": "Prototype pollution via unvalidated merge of user input",
            "severity": "HIGH",
            "category": "sast",
            "scanner": "semgrep",
            "rule_id": "javascript.lang.security.audit.prototype-pollution",
            "advisory_ref": "CWE-1321",
            "file_path": "app/routes/profile.js",
            "line_start": 27,
            "line_end": 32,
            "evidence": "_.extend(user, req.body)",
            "remediation": (
                "Never merge untrusted user input directly into objects. "
                "Use an allowlist of permitted fields, or use Object.assign with a sanitized copy."
            ),
            "source_url": None,
            "provenance": "scanner",
        },
        {
            "finding_id": "demo-004",
            "title": "Outdated express package with known vulnerabilities (illustrative)",
            "severity": "MEDIUM",
            "category": "dependency",
            "scanner": "trivy",
            "rule_id": "CVE-2022-24999",
            "advisory_ref": "CVE-2022-24999",
            "file_path": "package.json",
            "line_start": None,
            "line_end": None,
            "evidence": "express@4.16.4",
            "remediation": "Upgrade express to 4.18.2 or later.",
            "source_url": "https://nvd.nist.gov/vuln/detail/CVE-2022-24999",
            "provenance": "scanner",
        },
        {
            "finding_id": "demo-005",
            "title": "Missing HTTP security headers (helmet not configured)",
            "severity": "MEDIUM",
            "category": "misconfiguration",
            "scanner": "semgrep",
            "rule_id": "javascript.express.security.audit.xss.no-helmet",
            "advisory_ref": None,
            "file_path": "server.js",
            "line_start": 1,
            "line_end": 10,
            "evidence": "const express = require('express');\n// helmet not imported",
            "remediation": (
                "Install helmet (`npm install helmet`) and add `app.use(helmet())` "
                "before your routes to set secure HTTP headers."
            ),
            "source_url": None,
            "provenance": "scanner",
        },
    ],
}


DEMO_SCANNER_STATUS = {
    "trivy": {
        "available": False,
        "exit_code": None,
        "error_message": "Illustrative demo — no real scan performed",
        "finding_count": 0,
    },
    "semgrep": {
        "available": False,
        "exit_code": None,
        "error_message": "Illustrative demo — no real scan performed",
        "finding_count": 0,
    },
}


def build_demo_markdown(report: dict) -> str:
    lines = [
        "# RepoLens Security Audit: OWASP/NodeGoat",
        "",
        "> ⚠️ **ILLUSTRATIVE DEMO REPORT** — These findings were manually curated "
        "for demonstration purposes and were NOT produced by a live Trivy or Semgrep scan. "
        "Run a real scan to get verified results.",
        "",
        f"**Repository:** {DEMO_URL}",
        "**Tech Stack:** Node.js",
        "**Scanners:** Not run (demo mode)",
        "",
        "---",
        "",
        "## Findings Summary",
        "",
        "| Severity | Count |",
        "| --- | --- |",
        "| HIGH | 3 |",
        "| MEDIUM | 2 |",
        "| **Total** | **5** |",
        "",
        "---",
        "",
        "## Detailed Findings (Illustrative)",
        "",
    ]
    for f in report.get("findings", []):
        lines.append(f"### [{f['severity']}] {f['title']}")
        lines.append(f"- **Scanner:** {f['scanner']}")
        if f.get("rule_id"):
            lines.append(f"- **Rule:** {f['rule_id']}")
        if f.get("file_path"):
            loc = f["file_path"]
            if f.get("line_start"):
                loc += f":{f['line_start']}"
            lines.append(f"- **Location:** `{loc}`")
        if f.get("evidence"):
            lines.append(f"- **Evidence:** `{f['evidence']}`")
        if f.get("remediation"):
            lines.append(f"- **Remediation:** {f['remediation']}")
        lines.append("")

    lines += [
        "---",
        "",
        "*This is an illustrative demo report. Run RepoLens against a real repository to see verified scan results.*",
    ]
    return "\n".join(lines)


def seed():
    """Main seed function. Idempotent."""
    logger.info("Seeding demo report for %s", DEMO_URL)

    try:
        from backend.db import upsert_audit, get_audit_by_url
    except ImportError as exc:
        logger.error(
            "Cannot import backend.db — ensure you are running from the project root "
            "with the virtual environment activated: %s", exc
        )
        sys.exit(1)

    try:
        # Check if already seeded
        existing = get_audit_by_url(DEMO_URL)
        if existing and existing.get("is_demo"):
            logger.info(
                "Demo record already exists (id=%s). Updating to latest illustrative report.",
                existing["id"],
            )

        demo_markdown = build_demo_markdown(DEMO_REPORT)
        audit_id = upsert_audit(
            repository_url=DEMO_URL,
            repository_name=DEMO_REPO_NAME,
            commit_sha=DEMO_COMMIT_SHA,
            scan_status="completed",
            is_demo=True,
            report_json=DEMO_REPORT,
            report_markdown=demo_markdown,
            scanner_status=DEMO_SCANNER_STATUS,
        )
        logger.info("✅ Demo record upserted with id=%s", audit_id)
        logger.info(
            "   Note: This is an ILLUSTRATIVE report (is_demo=True). "
            "No real scan was performed."
        )
    except Exception as exc:
        logger.error("❌ Seeding failed: %s", exc)
        logger.error(
            "Ensure PostgreSQL is running and DATABASE_URL is configured in .env"
        )
        sys.exit(1)


if __name__ == "__main__":
    seed()
