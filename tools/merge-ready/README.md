# MergeReady

> Production-quality contribution validator for open-source AI agents and developer tools.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Reviewing open-source contributions to AI agent repositories requires tedious, error-prone manual verification of folder naming conventions, documentation completeness, secrets exposure, out-of-scope diff changes, dependency declarations, and hidden prompt vulnerabilities. Generic linters (e.g., Flake8, ESLint) lack repository-specific context, while conventional container runners require untrusted code execution.
- **Intended Users**: Open-source contributors verifying their pull requests before submission, and repository maintainers automating pre-merge PR triage and CI evaluation.

### Key Features
- **16 Repository-Specific Checks**: Validates folder structure (`agents/` vs `tools/`), kebab-case naming, template residue, required documentation sections, zero-secrets policy, diff scope, environment drift, dependency manifests, and agent safety heuristics.
- **Evidence-Backed Verdict Model**: Emits four explicit verdicts (`PASS`, `FAIL`, `WARN`, `SKIP`, `N/A`) inspired by Kibble, clearly differentiating checked passes from uncheckable environments.
- **Agent Guardrails & Static Safety**: Detects Trojan Source bidirectional overrides (`U+202A`–`U+202E`, `U+2066`–`U+2069`, CVE-2021-42574) that deceive human reviewers, Plane 14 Unicode tag characters (`U+E0000`–`U+E007F`) used for invisible prompt injection against LLMs, unbounded execution loops around model calls, and undisclosed high-impact tool capabilities (e.g. `subprocess`).
- **Fail-Safe Resource Limits**: Enforces strict bounds (`MAX_FILE_COUNT = 500`, `MAX_FILE_SIZE = 5 MB`, path-traversal symlink rejection). Exceeding bounds triggers explicit `ERROR` findings under `F01`—MergeReady fails closed and never silently omits uninspected files.
- **Diff Scope & Index Table Validation**: Validates Git three-dot diffs (`<base>...HEAD`) to guarantee that contributions never modify unrelated repository files.
- **Multi-Format Reporting**: Produces human-readable terminal output, strictly valid JSON for automation, GitHub-flavored Markdown for PR summaries, and inline GitHub Actions annotations (`::error`, `::warning`).
- **Zero Secrets Disclosure**: Automatically redacts candidate credentials, keys, and tokens in evidence strings and reports.
- **Offline & Self-Contained**: Requires no LLM API keys, no network access, and never executes untrusted contributor code.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+
- **Agent Framework / Core Library**: Python Standard Library (`ast`, `tomllib`, `subprocess`, `argparse`, `dataclasses`, `re`, `pathlib`)
- **Models**: None (deterministic static analysis)
- **External APIs / Tools**: Git CLI (optional, used for diff scope and tracked file discovery)

---

## Architecture & Data Flow

```
[Project Path / Git Ref]
          │
          ▼
  [ProjectContext] ───► Discovers Repo Root, Category & Slug
          │        ───► Loads rules.toml & Runtime Template
          │        ───► Gathers Tracked & Workspace Files
          ▼
   [Check Engine]
   ├─► Layout & Naming Checks (L01, L02, F01)
   ├─► Documentation & Template Residue (D01, D02, R02)
   ├─► Zero-Secrets & Entropy Analyzer (S01, S02)
   ├─► Merge-Base Diff Scoper (P01, I01)
   ├─► AST Environment & SDK Disclosures (E01, E02)
   ├─► Dependency Manifest Analyzer (R01)
   └─► Agent Safety & Guardrail Scanners (A01, A02, A03)
          │
          ▼
 [ValidationReport] ───► PASS / FAIL / WARN / SKIP / N/A
          │
   [Report Formatter]
   ├─► Terminal (Ansi-styled inspection summary)
   ├─► JSON (Machine-readable CI output)
   ├─► Markdown (GitHub Step Summary & PR comments)
   └─► GitHub Annotations (Inline PR reviews)
```

---

## Prerequisites

- Python 3.11 or later
- pip package manager
- Git (optional, required only for `--base` diff scope validation)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/merge-ready
   ```

2. **Set up the virtual environment & install in editable mode:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -e .
   ```

3. **Configure Environment Variables (Optional):**
   ```bash
   cp .env.example .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `LOG_LEVEL` | No | `info` | Optional logging verbosity level (`debug`, `info`, `warn`) |

*Note: MergeReady operates completely offline and requires no third-party API keys or secret credentials.*

---

## How to Run

### Command Syntax

```bash
# Basic project validation
merge-ready check tools/<your-tool>

# Validate against upstream main base reference
merge-ready check tools/<your-tool> --base upstream/main

# Export JSON report
merge-ready check tools/<your-tool> --format json --output report.json

# Export GitHub Step Summary Markdown
merge-ready check tools/<your-tool> --format markdown --output summary.md

# Enforce strict mode (fail on warnings or skips)
merge-ready check tools/<your-tool> --strict
```

### Exit Codes

| Code | Meaning |
| :--- | :--- |
| `0` | Success: All evaluated checks passed with zero failing errors (and zero warnings under `--strict`). |
| `1` | Validation Failure: One or more rules failed, or warnings/skips occurred under `--strict`. |
| `2` | Operational Error: Invalid arguments, missing project directory, or fatal execution error. |

---

## Example Input & Output

### Example Command

```bash
merge-ready check tools/merge-ready/tests/fixtures/good-tool
```

### Example Output

```text
========================================================================
  MergeReady Contribution Validator — tools/good-tool
========================================================================

  [PASS]   L01: Dedicated Directory Location
  [PASS]   L02: Naming Conventions
  [PASS]   F01: Required File Standards
  [PASS]   D01: Template Residue Detection
  [PASS]   D02: Required Documentation Sections
  [PASS]   S01: Zero Secrets Policy
  [PASS]   S02: No Virtual Environments or Local Databases
  [SKIP]   P01: Contribution Diff Scope (No Git base reference provided (--base <ref>). Scope check skipped.)
  [SKIP]   I01: Category Index Entry (Git base reference or repository root not available.)
  [PASS]   E01: Environment Variable Drift
  [N/A]    E02: Paid API and Model Disclosure (No known paid model provider SDKs imported.)
  [PASS]   R01: Declared Dependency Manifest
  [PASS]   R02: README Command References Consistency
  [PASS]   A01: Unbounded Execution Loops
  [PASS]   A02: Hidden and Deceptive Unicode
  [N/A]    A03: High-Impact Capabilities Disclosure (No high-impact shell or code execution calls detected.)

------------------------------------------------------------------------
Summary: 12 pass · 0 fail · 0 warn · 2 skipped · 2 n/a
Result: PASSED — Contribution meets all checked repository standards.
------------------------------------------------------------------------
```

---

## How to Test

Run the full automated test suite using `pytest`:

```bash
# Run all unit, fixture, and integration tests
pytest tools/merge-ready/tests -v
```

The test suite covers:
- Verification of golden-clean contributions (`good-tool`).
- Detection of intentional rule violations via runtime-constructed temporary fixtures (avoiding committed secrets, databases, or bidi characters).
- Negative controls (UUIDs, Git commit SHAs, template placeholders).
- Decoupled detection of Trojan Source BiDi (CVE-2021-42574) and Plane 14 tag prompt injections.
- Fail-safe enforcement of scan limits (`MAX_FILE_COUNT > 500`, `MAX_FILE_SIZE > 5 MB`, path-traversal symlinks).
- Deep scanning across nested fixture directories without blanket exemptions.
- Three-dot Git merge-base scope enforcement.
- CLI argument parsing, output format stability, and exit codes.

---

## Known Limitations

- **Language Parsing Depth**: Static AST inspection for environment variable reads and unbounded loops currently analyzes Python files (`.py`) and basic JavaScript/TypeScript patterns (`process.env`). Projects in Go or Rust undergo file-level, secret, Unicode, template, and scope validation, but language-level AST analysis is not yet supported.
- **Dynamic Variable Names**: Dynamically constructed environment variable names (e.g., `os.getenv(f"KEY_{env}")`) cannot be resolved statically and are skipped to prevent false errors.
- **Static Heuristic Scope**: MergeReady validates contribution compliance, structure, and static safety. It does not evaluate semantic algorithmic accuracy, model output coherence, or replace human review.
- **Dependency Version Resolution**: Dependency checks verify that imported top-level modules are declared in the project manifest, but do not resolve deep transitive dependency conflicts.

---

## Security & Privacy Considerations

MergeReady implements strict defensive guardrails:

1. **Untrusted Code Isolation (No Code Execution)**:
   - MergeReady **never imports, executes, or installs** the code under review.
   - All code analysis is performed via static Abstract Syntax Trees (AST) or token parsing.
2. **Denial-of-Service (DoS) Guardrails & Fail-Safe Scans**:
   - Caps individual file read size at **5 MB** (`MAX_FILE_SIZE`).
   - Limits directory scanning to **500 files** (`MAX_FILE_COUNT`).
   - Refuses symlinks that resolve outside the project directory boundary.
   - **Fail-Closed Guarantee**: Any project exceeding file count, file size, or symlink boundaries triggers explicit `ERROR` findings under `F01` and fails validation. MergeReady never silently drops files or declares truncated scans clean.
3. **Deceptive Unicode Defense**:
   - Trojan Source (`U+202A`–`U+202E`, `U+2066`–`U+2069`, CVE-2021-42574): Prevents visual reordering attacks that mislead human code reviewers.
   - Plane 14 Unicode Tags (`U+E0000`–`U+E007F`): Detects and decodes invisible ASCII character streams used for prompt injection attacks against LLMs.
4. **Zero Secrets Disclosure**:
   - When candidate credentials or high-entropy tokens are detected, MergeReady redacts sensitive values (e.g. `AIza...XXXX [REDACTED]`) before rendering terminal output, JSON, or Markdown reports.
5. **Committed Fixture Hygiene**:
   - Test suites construct security-sensitive fixtures dynamically in temporary `tmp_path` directories at runtime using string concatenation and `chr()`, ensuring no API keys, bidi overrides, or binary SQLite databases are committed into Git.
6. **Read-Only Non-Destructive Operation**:
   - MergeReady never alters repository files, never writes to Git history, and never modifies the Git index during validation.
7. **Safe CI Execution**:
   - The provided GitHub Actions workflow uses the standard `pull_request` event with read-only permissions (`permissions: contents: read`). It avoids `pull_request_target` to eliminate fork-hijacking attack vectors.

---

## Future Improvements

- [ ] AST parsing support for TypeScript and Go agents.
- [ ] Integration with Gitleaks binary when locally available for extended secret heuristics.
- [ ] Automated suggestion of missing index row markdown snippet.

---

## Contributor & Attribution

- **Author / Contributor**: [@Rithvik-krishna](https://github.com/Rithvik-krishna)
- **Repository**: [open-source-agents](https://github.com/gdgcblr/open-source-agents)

---

## License

This project is contributed under the repository's open-source license (MIT License © 2026 GDG Cloud Bengaluru Community).
