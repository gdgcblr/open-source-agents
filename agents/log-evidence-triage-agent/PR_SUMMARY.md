# feat(agents): upgrade TraceTriage to evidence-driven TraceGuard AI

## Project overview

- **Project:** TraceGuard AI
- **Category:** `agents/log-evidence-triage-agent`
- **Technologies:** Python 3.12, Google ADK, Gemini, standard-library offline evaluation

Application incident triage now correlates explicit PHP/Node.js runtime versions with a small verified October 2026 advisory snapshot and returns cited findings, unknowns, and deterministic PASS/HOLD/ESCALATE decisions. Existing operational log detectors remain available. AI can select canonical findings but cannot introduce unsupported prose, fabricate citations, or override escalation. API failures retain labeled deterministic reports.

Report schema 2 separates FIXED_FOR_CHECKED_ADVISORIES from OVERALL_SECURITY_UNKNOWN and exposes snapshot freshness, publication dates, and structured coverage gaps. Known unevaluated records/notices and stale data require HOLD unless escalation takes precedence. No live CVE crawler is introduced.

Includes advisory provenance, a report-local evidence ledger, input bounds and redaction, structured ADK input, human escalation packages, 18 golden scenarios, negative/safety tests, pinned dependencies, synthetic samples, and contributor documentation.

## Validation

- Baseline: 8/8 original tests passed on Windows 11/Python 3.12.10.
- Full final suite: **176/176 passed, 0 failed, 0 skipped** with ADK installed.
- Dependency-free run: **169 passed, 0 failed, 7 optional ADK tests skipped**.
- Golden outcomes: version matching 18/18; citation validity 18/18; mandatory escalation 8/8; repeated output consistency 18/18; zero unsupported confirmed-compromise assertions.
- Seven offline integration tests use the real ADK runner and a fake model. One recorded live synthetic Gemini Flash Lite smoke run before the schema 2 refinement returned a validated selection.
- `pip check`: no broken requirements. Demo scenarios produced ESCALATE/AFFECTED, PASS/FIXED_FOR_CHECKED_ADVISORIES with coverage warning, and HOLD/FIXED_FOR_CHECKED_ADVISORIES as expected.
- Full case results and limitations: `evaluations/report.json` and `evaluations/README.md`.

## Contribution checklist

- [x] Changes isolated to the existing lowercase kebab-case agent folder.
- [x] README covers all applicable upstream template sections and reproducible commands.
- [x] Offline setup and clean optional dependency installation exercised on Windows.
- [x] Synthetic inputs and actual output artifacts included.
- [x] Dependencies declared; full installed version snapshot included.
- [x] `.env`, virtual environment, caches, and local ADK storage ignored.
- [x] No automatic remediation, paging, commits, pushes, or PR creation.

## Limits and reviewer follow-up

Review the three-CVE snapshot and its branch assumptions. PHP's October 23 follow-up remains a documented HOLD condition. This is not a complete scanner, deployment attestation, DLP system, or forensic compromise detector. Linux/macOS/Docker and Vertex AI are untested. Live provider observations are not an accuracy benchmark. Review branch ancestry against current upstream `main` before submission and use the upstream PR template when opening the PR.
