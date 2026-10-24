# First PR Copilot 

> A pre-flight code hygiene auditor and PR description generator built to help first-time open-source contributors submit confident, clean, maintainer-grade pull requests.

---

##  Overview

Contributing to open-source repositories can be intimidating for newcomers. First-time pull requests are frequently delayed, blocked, or rejected due to easily preventable mistakes:
- Accidental debug logging statements (`console.log`, `print()`, `debugger;`)
- Unresolved `TODO` comments left behind in the diff
- Accidental credential or API key exposures
- Blank or low-detail PR descriptions that omit testing and validation steps

**First PR Copilot** runs an automated pre-flight scan over code changes before submission, computes an objective readiness score (0–100%), and generates an industry-standard, maintainer-friendly PR description in clean Markdown.

---

## Category

- **AI Automation & Developer Utilities** (CI Helpers, Pre-flight Linters, and Git Utilities)

---

## Key Features

- **Automated Hygiene Scan:** Inspects staged code diffs against common patterns for debug logs, unaddressed `TODO` flags, and credential leaks.
- **Readiness Scoring:** Generates an immediate 0–100% pre-flight score to give contributors confidence before opening a PR.
- **Maintainer-Grade PR Formatter:** Automatically generates formatted PR descriptions with clear summaries, security checklists, and step-by-step reproduction instructions.
- **Zero External Dependencies:** Implemented in native Node.js (ES modules), requiring no external packages or complex toolchains.

---

## Directory Structure

```text
tools/first-pr-copilot/
├── .env.example       # Environment configuration template
├── .gitignore          # Ignores node_modules, local secrets, and logs
├── package.json        # Project metadata and execution scripts
├── index.js            # Core scanner logic and PR template formatter
└── README.md           # Project documentation and usage guide