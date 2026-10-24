# UAT & E2E Test Generator Agent

> Automatically converts hardened product requirements into structured, executable User Acceptance Testing (UAT) and End-to-End (E2E) test cases in strictly tabular format.

## Overview

### Problem Statement & Intended Users

* **Problem**: Translating Product Requirements Documents (PRDs) into comprehensive test cases manually is slow, error-prone, and often results in missed edge cases and poor requirements traceability.
* **Intended Users**: Quality Assurance (QA) Engineers, Test Automation Engineers, Product Owners, and Software Developers.

### Key Features

* **Direct PRD & Pipeline Integration**: Operates seamlessly downstream from the `requirements-hardener` agent or consumes hardened PRDs directly.
* **Strict Requirements Traceability**: Maps every single test case directly back to a specific requirement ID (e.g., `REQ-01`).
* **Strict Tabular Formatting**: Generates test suites exclusively in standardized tabular formats (Markdown tables or exported Excel files) with explicit `PASS/FAIL` execution fields.

---

## Technical Stack

* **Language & Runtime**: Python 3.11+ / Node.js 20+
* **Agent Framework / Core Library**: Open-Source Agents Framework / Markdown Skill Protocol
* **Models**: Gemini 2.5 Flash / Claude 3.5 Sonnet / GPT-4o
* **External APIs / Tools**: Pandas / OpenPyXL (Excel Export), Markdown Table Generators

---

## Architecture & Data Flow

```
[Hardened PRD / Requirements Stream]
                  |
                  v
  [Requirement & Scenario Extraction]
                  |
                  v
     [UAT Test Generator Agent]
    ├── 1. Scenario Coverage Mapping
    ├── 2. Pre-condition & Step Synthesis
    └── 3. Evidence & Comments Formatting
                  |
                  v
    [Interactive Clarification / Sign-off]
                  |
                  v
  [Tabular Test Suite (Markdown / .xlsx)]
```

---

## Prerequisites

Before running this project, ensure you have:

* Python 3.11+ or Node.js 20+
* Package manager (`pip` or `npm`)
* `GEMINI_API_KEY` or equivalent LLM provider key configured in environment variables

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/uat-test-generator
   ```

2. **Set up the virtual environment / install dependencies:**
   * For Python:
     ```bash
     python -m venv .venv
     # Windows:
     .venv\Scripts\activate
     # Linux/macOS:
     source .venv/bin/activate

     pip install -r requirements.txt
     ```
   * For Node.js / TypeScript:
     ```bash
     npm install
     ```

3. **Configure Environment Variables:**
   Copy the example environment file and fill in your keys:
   ```bash
   cp .env.example .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes | *None* | API key for Gemini / LLM provider |
| `MODEL_NAME` | No | `gemini-2.5-flash` | LLM model identifier used for analysis |
| `OUTPUT_FORMAT` | No | `markdown` | Preferred table format (`markdown` or `excel`) |
| `LOG_LEVEL` | No | `info` | Verbosity level (`debug`, `info`, `warn`, `error`) |

---

## How to Run

```bash
# Process a hardened PRD markdown file and generate UAT test table
python main.py --input path/to/hardened_prd.md

# Generate test suite as an Excel file (.xlsx)
python main.py --input path/to/hardened_prd.md --format excel --output path/to/test_suite.xlsx

# Run interactively with clarify-and-approval guardrails
python main.py --interactive
```

---

## Example Input & Output

### Example Input
> Process hardened PRD section for `REQ-01` (System Theme Detection) and `REQ-02` (Manual Settings Toggle).

### Example Output

| The Requirements ID | PASS/FAIL Drop down | Scenario | Detailed Steps | Evidence | Comments |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **REQ-01** | `[ PASS \| FAIL ]` | Verify app automatically detects system Dark Mode on launch. | 1. Set device OS setting to Dark Mode.<br>2. Freshly launch application.<br>3. Verify home screen renders in Dark Mode. | `[Pending attachment]` | Check instant rendering on application boot. |
| **REQ-02** | `[ PASS \| FAIL ]` | Verify user manual theme override via Settings. | 1. Set OS to Light Mode.<br>2. Open app -> Settings -> Appearance.<br>3. Select Dark Mode.<br>4. Restart app and verify persistence. | `[Pending attachment]` | Ensure theme choice persists across app restarts. |

---

## How to Test

```bash
# Run automated test suite
pytest

# Test tabular generation logic without making API calls
pytest tests/test_table_generator.py
```

---

## Known Limitations

* Requires a structured or hardened requirement document with clear Requirement IDs for optimal traceability mapping.
* Visual/UI comparison steps require manual screenshot attachment during QA execution.

---

## Security & Privacy Considerations

* **Secrets Handling**: All API keys are loaded via environment variables and never logged or hardcoded.
* **Data Privacy**: Requirements and generated test plans stay within configured environment boundaries.
* **Safety**: Read-only processing on source PRD inputs; outputs new test artifacts only upon user approval.

---

## Future Improvements

* [ ] Direct sync with TestRail, Xray, and Jira Test Management.
* [ ] Automatic export to downloadable `.xlsx` files with native dropdown elements for `PASS/FAIL`.
* [ ] Integration with Playwright / Cypress for auto-generating executable code stubs.

---

## License

*This project is contributed under the repository's open-source license.*