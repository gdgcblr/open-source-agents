# PR Security Auditor Task List

Implemented checkboxes indicate code or documentation exists; they do not imply tests were run.

## Phase 1: Required MVP

- [x] Create a self-contained Python project and CLI.
- [x] Support staged, working-tree, and base-ref diff scopes.
- [x] Scan added lines locally for common credentials and risky code patterns.
- [x] Redact credential values from local findings.
- [x] Check supported exact dependency versions against OSV.
- [x] Require Google Gemini LLM review after local checks.
- [x] Enable Gemini Google Search grounding for current vulnerability research on every LLM request.
- [x] Filter secret-matching and oversized lines and bound the hosted context.
- [x] Mask common PII and anonymize file paths before hosted review.
- [x] Validate model findings against submitted locations and verified grounding citations.
- [x] Suggest remediation options for local, OSV, and LLM findings without applying fixes.
- [x] Generate Markdown reports with sources and external-service disclosure.
- [x] Add mocked OSV/Gemini API tests that need no network or real credentials.
- [x] Document setup, API-key configuration, privacy implications, and limitations.
- [x] Run the complete unit suite on Python 3.10+ and resolve failures.
- [ ] Smoke-test the installed CLI in a disposable Git repository for staged, working-tree, base-ref, reporting, and exit-code behavior.

## Phase 2: Reliability and Coverage

- [ ] Add integration tests using temporary repositories for staged/working-tree diffs, deleted files, quoted paths, and base-ref comparisons.
- [ ] Refine secret patterns with positive and negative fixtures; verify no secret appears in reports, logs, or model output.
- [ ] Improve requirements parsing for editable, URL, constraint-file, and environment-marker forms.
- [ ] Add lockfile support for `poetry.lock`, `uv.lock`, `Pipfile.lock`, `package-lock.json`, and `yarn.lock`.
- [ ] Add transitive dependency checks for supported lockfiles.
- [ ] Improve package name/version normalization and cover scoped npm packages and prereleases.
- [ ] Include confirmed fixed-version guidance and advisory references from OSV where available.
- [ ] Add JSON report output for CI and deterministic output apart from timestamps.
- [ ] Add tests for rate limits, web-search failures, missing/invalid citations, output errors, large changes, and partial API failures.
- [ ] Review model fix suggestions against safe coding guidance; ensure suggestions are explicitly non-automated.

## Phase 3: Workflow Integration

- [ ] Add a documented pre-commit hook example that invokes the required staged audit without installing hooks automatically.
- [ ] Add a GitHub Actions usage example with pinned action dependencies and required API-key secret setup.
- [ ] Document Gemini API pricing, free-tier limits, and Google Search grounding quotas.
- [ ] Document false-positive triage, hosted-code data policies, and report-sharing precautions.
- [ ] Add repository rule configuration with secure defaults and tests.
- [ ] Define release/versioning policy and supported Python/manifest compatibility.

## Acceptance Criteria

- A complete run requires Git, network access, and `GEMINI_API_KEY`; missing required services produce exit status `2`.
- Every complete run performs local checks, relevant OSV dependency checks, and Gemini review with Google Search grounding.
- Current vulnerability claims from the LLM include verified citations from Gemini grounding metadata.
- Findings have actionable suggested fixes and sources where applicable; fixes are never applied automatically.
- Credential values do not appear in reports or diagnostics, and secret-matching lines are excluded from hosted context.
- Common PII patterns are masked and source paths anonymized before hosted LLM review; documentation states this is heuristic.
- OSV receives package metadata only; Gemini receives only bounded eligible code context and dependency metadata.
- Unit tests run without network access and cover parsers, redaction, API responses, citations, reports, and Git scopes.
- Documentation describes heuristic limits and does not present a clean scan as proof of security.
