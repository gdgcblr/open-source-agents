# PR Security Auditor Design

## 1. Purpose

PR Security Auditor reviews Git changes before commit or merge. It combines deterministic local checks, OSV dependency queries, and a required Google Gemini LLM review grounded by Google Search. It reports findings, possible fixes, and sources for a human to verify.

The tool does not modify code, automatically apply fixes, or claim that a clean scan proves a change is secure.

## 2. Goals and Non-Goals

### Goals

- Scan added lines from staged changes, working-tree changes, or a diff against a base ref.
- Detect common credential formats and recognizable risky code patterns locally.
- Check exact versions in changed `requirements.txt` and `package.json` files against OSV.
- Require Google Gemini LLM review for code quality and security after the local checks.
- Enable Google Search grounding on every Gemini request to ground recent public vulnerability analysis in current internet results.
- Include practical suggested remediations and cited sources; never apply fixes automatically.
- Keep secrets out of reports and exclude locally detected secret lines from hosted LLM input.
- Return clear exit codes and mark incomplete external checks as incomplete.

### Non-Goals

- Replacing static analyzers, secret scanners, software composition analysis, or a human security review.
- Proving that a reported issue is exploitable or that unreported code is safe.
- Resolving dependency graphs, ranges, lockfiles, or transitive dependencies in the current implementation.
- Automatically changing source files, staging changes, committing, or pushing.
- Executing code, commands, or tools based on diff content.

## 3. Primary Workflows

1. `pr-security-auditor --staged` reviews staged changes.
2. `pr-security-auditor` reviews tracked working-tree changes relative to `HEAD`.
3. `pr-security-auditor --base origin/main` reviews the working tree against a base ref.
4. Every run performs local checks, applicable OSV checks, then a required Gemini review grounded by Google Search.
5. The user reviews all findings, fixes, and citations and chooses whether to make changes.

A complete run requires `GEMINI_API_KEY` and working access to Google Gemini. There is no successful offline mode. If a required external check cannot complete, the report and exit code must indicate an incomplete audit.

Gemini API usage and Google Search grounding have quotas and may incur charges; users should review current pricing and free-tier limits.

## 4. Architecture

```text
CLI
 |
 v
Audit coordinator
 +--> Git adapter --> unified diff + changed paths + staged manifest content
 +--> Diff parser --> local secret checks + risky-code patterns
 +--> Manifest parser --> exact package versions --> OSV batch query
 +--> LLM input filter --> Gemini Interactions API + Google Search grounding
 |                         +--> code-quality/security review
 |                         +--> current public vulnerability research
 |                         +--> fix suggestions and cited sources
 v
Validated findings and audit notes
 +--> Markdown report
 +--> exit status
```

The current implementation keeps the components as functions in `src/pr_security_auditor.py`, with unit-testable parsing, matching, API handling, and report generation.

## 5. Data Flow

### 5.1 Local diff checks

1. Select staged, default working-tree, or base-ref comparison.
2. Invoke Git using argument arrays rather than a shell.
3. Parse added lines and their new-file line numbers.
4. Run local secret and risky-code pattern checks.
5. Store generic redacted findings; never retain matched credential values.

### 5.2 Dependency vulnerability checks

1. Identify changed `requirements.txt` and `package.json` files.
2. Read staged manifest content from the Git index in staged mode; otherwise read the working-tree file.
3. Parse exact versions supported by the current implementation. Report unsupported/ranged specifications instead of implying they were checked.
4. Send only ecosystem, package name, and version to OSV. Never send source code, diff text, file paths, or credentials.
5. Convert advisory results into findings, including severity where available, suggested upgrade guidance, and HTTPS advisory references.
6. A network or response error is an audit error, not a clean result.

### 5.3 Required Google Gemini review

1. Require `GEMINI_API_KEY`; read `GEMINI_MODEL` if set, otherwise use `gemini-3.8-flash`.
2. Exclude added lines that match local secret patterns or exceed 1,000 characters. Mask common emails, phones, street addresses, names in common fields and title-cased full-name-like text; anonymize file paths and bound the total submitted context.
3. Send eligible masked added lines, exact dependency metadata, and non-secret local finding summaries with anonymized paths.
4. Enable the Gemini API's Google Search grounding tool on each request.
5. Ask the model for concrete code-quality/security findings, up to three practical fix options per finding, and sources. Claims about CVEs, vulnerabilities, or advisories must cite HTTPS URLs returned in Gemini's grounding metadata.
6. Treat code and comments as untrusted input. Do not provide model tools or code execution.
7. Validate response JSON, finding severity, fix options, verified HTTPS grounding sources, and exact path/line membership in submitted changes.
8. Missing API credentials, failed requests, absent Google Search citations, or unusable responses make the audit incomplete.

Google Search grounding improves recency but cannot guarantee that every newly published vulnerability is indexed or found. Dependency checks remain limited to the manifests and versions that the tool supports.

### 5.4 Suggested fixes and reporting

- Local pattern findings use rule-specific guidance, such as rotating leaked credentials or using parameterized SQL.
- OSV findings recommend upgrading to a version confirmed as unaffected by the advisory.
- LLM findings provide up to three viable remediation options; current vulnerability claims include verified Google Search citations.
- Suggestions are advisory only and require human verification.
- The Markdown report includes severity, type, location, evidence, suggested fixes, sources, audit notes, and generation time.
- If Google Gemini was attempted, disclose provider and model. Never place the API key in reports or errors.
- Return `0` for a clean, complete scan; `1` for findings after a complete scan; `2` for missing or failed required checks or report-writing errors.

## 6. Finding Model

| Field | Meaning |
| --- | --- |
| `severity` | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, or `UNKNOWN` |
| `category` | Finding type such as `Secret`, `Interpolated SQL`, or `Vulnerable dependency` |
| `path` | Repository-relative file path |
| `line` | New-file line number where applicable |
| `message` | Brief evidence-based description without credential values |
| `remediation` | One or more suggested fixes; never applied automatically |
| `references` | Verified HTTPS advisory or Google Search grounding sources where applicable |

Audit notes are separate from findings and explain unsupported manifests or incomplete checks. They must not imply that unperformed checks passed.

## 7. Security, Privacy, and Reliability

- Local checks never execute diff content.
- Git is invoked without a shell; base refs are validated.
- Manifest paths must resolve inside the repository before access.
- OSV receives package metadata only. Google Gemini receives eligible added source lines and dependency metadata because hosted LLM review is mandatory.
- Locally matched secret lines and oversized lines are excluded from LLM input. Common PII patterns are masked, and file paths are anonymized. These heuristics cannot guarantee sensitive data removal; they may miss unusual name, address, or phone formats and may mask benign proper names.
- Reports and diagnostics must not reveal the API key or detected credential values.
- Model output and search-derived citations are untrusted and validated before report inclusion.
- Bound context, request timeouts, API batches, result counts, and report size.
- Clearly disclose hosted code processing and require human validation of findings and fixes.

## 8. Testing Strategy

- Unit-test diff parsing, line numbering, secret detection/filtering, and each risky-code rule.
- Test manifest parsing, unsupported specifications, malformed input, path traversal protection, and staged-index reads.
- Mock OSV and Google Gemini responses; tests must not require network access or real credentials.
- Test Google Search grounding request construction, missing citations, citation validation, finding/fix shape validation, and API failures.
- Use temporary repositories for staged, working-tree, and base-ref integration tests.
- Test report escaping, source links, output destinations, and exit codes for clean, findings, and incomplete runs.
- Run unit tests on Python 3.10+ and manually smoke-test the installed CLI in a disposable repository before release.

## 9. Current MVP Status

The implementation includes local pattern checks, exact-version OSV queries, a required Google Gemini request with Google Search, filtering and validation of model input/output, fix suggestions, Markdown reporting, and mocked API tests.

The unit suite is run with Python 3.10+ and uses mocked external responses. Lockfile/transitive dependency support, broader manifest formats, Git-hook integration, and CI-specific output remain follow-up work.
