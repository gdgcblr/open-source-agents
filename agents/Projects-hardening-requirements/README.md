# Requirements Hardener Agent

> Automatically evaluates, audits, and hardens product requirements documents into structured, testable specifications with version history tracking and strict guardrails.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Raw Product Requirement Documents (PRDs), feature briefs, and user stories are often ambiguous, incomplete, or redundant. This leads to scope creep, developer misalignment, and untestable features.
- **Intended Users**: Product Managers, Technical Program Managers, Business Analysts, and Software Engineering Leads.

### Key Features
- **Multi-Format Ingestion**: Ingests requirements documents in any format (Word, Excel, PowerPoint, Markdown, or plain text) or integrates directly into existing product management pipelines.
- **Strict Guardrails & Dynamic Scaling**: Makes zero unverified assumptions (asks clarifying questions), dynamically scales processing passes based on document size, and enforces explicit user sign-off before committing changes.
- **Standardized Output & Traceability**: Structures output into 7 core sections (Business Context, Scenarios, In-Scope/Out-of-Scope, Detailed Requirements, Mapped Acceptance Criteria, Relevant Documentation, and Version History).

---

## Technical Stack

- **Language & Runtime**: Python 3.11+ / Node.js 20+
- **Agent Framework / Core Library**: Open-Source Agents Framework / Markdown Skill Protocol
- **Models**: Gemini 2.5 Flash / Claude 3.5 Sonnet / GPT-4o
- **External APIs / Tools**: File Parsers (Docx, Xlsx, Pptx, Markdown)

---

## Architecture & Data Flow

```
[Raw Requirement File/Pipeline Stream]
                  |
                  v
       [Ingestion & Parsing]
                  |
                  v
    [Requirements Hardener Agent]
    ├── 1. Analyze & Audit
    ├── 2. Detect Duplicates
    ├── 3. Dynamic Scaling (Sub-agents)
    └── 4. Harden & Format
                  |
                  v
    [Interactive Clarification / Approval]
                  |
                  v
[Structured Document + Version History]
```

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.11+ or Node.js 20+
- Package manager (`pip` or `npm`)
- `GEMINI_API_KEY` or equivalent LLM provider key configured in environment variables

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/requirements-hardener
   ```

2. **Set up the virtual environment / install dependencies:**
   - For Python:
     ```bash
     python -m venv .venv
     # Windows:
     .venv\Scripts\activate
     # Linux/macOS:
     source .venv/bin/activate

     pip install -r requirements.txt
     ```
   - For Node.js / TypeScript:
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
| `ENABLE_PIPELINE_MODE` | No | `false` | Enable strict programmatic execution for CI/CD or PM tool pipelines |
| `LOG_LEVEL` | No | `info` | Verbosity level (`debug`, `info`, `warn`, `error`) |

---

## How to Run

```bash
# Process a raw requirement document file
python main.py --input path/to/prd.docx

# Process markdown file with pipeline output
python main.py --input path/to/feature_brief.md --out-format markdown

# Run interactively with clarify-and-approval prompt guardrail
python main.py --interactive
```

---

## Example Input & Output

### Example Input
> *"We need a dark mode feature for our mobile app so users don't strain their eyes at night. Also make it sync with device settings. Make sure it works on iOS and Android. Also maybe add a quick toggle in settings. Released next sprint."*

### Example Output
```markdown
# Dark Mode Feature Requirement Specification

## 1. Business Context
- **Problem**: Users experience eye strain when using the app in low-light environments.
- **Product Goal**: Implement native Dark Mode across iOS and Android platforms to improve visual comfort and reduce battery consumption on OLED screens.

## 2. Scenarios
- **Device Sync**: App automatically matches device OS dark appearance settings.
- **Manual Toggle**: User manually selects Dark Mode inside App Settings.

## 3. In-Scope and Out of Scope Sections
- **In-Scope**: System-level theme sync (iOS 13+, Android 10+), Settings UI toggle, core color token updates.
- **Out of Scope**: Web application theme changes, user-defined accent colors.

## 4. Detailed Requirements
- **REQ-01**: System Theme Detection upon initial launch.
- **REQ-02**: Manual theme override via Settings toggle (System Default / Light / Dark).

## 5. Acceptance Criteria
- **Mapped to REQ-01**: Given OS is in Dark Mode, when app launches, then UI renders dark palette automatically.
- **Mapped to REQ-02**: Given user toggles theme manually, when saved, then app switches theme in < 100ms without app restart.

## 6. Relevant Documentation
- Design Tokens Reference: `/docs/design-tokens-v2.md`

## 7. Version History
- **v1.0 (2026-10-24)**: Initial raw brief.
- **v1.1 (2026-10-24)**: Hardened specification generated by `requirements-hardener` agent.
```

---

## How to Test

```bash
# Run automated unit and integration test suite
pytest

# Test document parsing and formatting without making API calls
pytest tests/test_parser.py
```

---

## Known Limitations

- Multi-megabyte document inputs with embedded images may require pre-processing or OCR extraction.
- Pipeline non-interactive mode requires pre-filled configuration for ambiguous business rules.

---

## Security & Privacy Considerations

- **Secrets Handling**: All API tokens are loaded securely via environment variables and never written to logs or output files.
- **Data Privacy**: Requirement documents sent to LLM endpoints are processed according to enterprise privacy flags; no proprietary product details are cached publicly.
- **Safety**: The agent operates in a read-transform-propose lifecycle and will not overwrite original files without explicit user sign-off.

---

## Future Improvements

- [ ] Direct integration with Jira, Linear, and Notion pipelines.
- [ ] Automated downstream generation of test suites via integration with `uat-test-generator`.
- [ ] Export directly to PDF, Word, and Confluence formats.

---

## License

*This project is contributed under the repository's open-source license.*