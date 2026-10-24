# 🩺 README Doctor — AI Documentation Checker

**Category:** AI Developer Utilities  
**Directory:** `tools/readme-doctor`

## Overview
**README Doctor** is a lightweight, language-agnostic command-line utility that scans any project's `README.md` to verify whether it includes essential developer documentation sections:
1. **Prerequisites**
2. **Installation**
3. **Configuration**
4. **Usage Examples**
5. **Troubleshooting & Limitations**

It combines fast, deterministic Markdown structure analysis with the **Google Gemini API** (`google-genai`) to compute a **Documentation Health Score (0–100)**, point out specific documentation gaps, and generate ready-to-paste Markdown templates for missing sections.

## Features
- **Missing Section Detection:** Instantly flags missing setup, configuration, usage, or troubleshooting sections.
- **Actionable LLM Feedback:** Uses `gemini-2.5-flash` to critique clarity and generate custom starter snippets.
- **Offline Static Mode:** Supports `--offline` execution for zero-cost CI/CD checks without an API key.
- **Report Export:** Outputs directly to the terminal or saves a structured Markdown report via `--output`.
- **CI-Friendly Exit Code:** `--fail-on-missing` returns status 2 if a required section is missing.

## Prerequisites
- **Python 3.10+**
- For AI suggestions, a **Google Gemini API key** from [Google AI Studio](https://aistudio.google.com/). Static checks work without a key.

## Installation

1. Navigate to the project directory:
   ```bash
   cd tools/readme-doctor
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Open `.env` and add your Gemini API key:
   ```ini
   GEMINI_API_KEY=your_actual_api_key_here
   ```

## Usage Examples

### 1. Scan a `README.md` with AI Suggestions
Pass either a specific `README.md` file or a project directory:
```bash
python readme_doctor.py ../../README.md
```

### 2. Save the Quality Report to a File
```bash
python readme_doctor.py ./README.md --output quality_report.md
```

### 3. Run Deterministic Checks Only (No API Key Needed)
```bash
python readme_doctor.py ./README.md --offline
```

### 4. Use in CI and fail when sections are missing
```bash
python readme_doctor.py ./README.md --offline --fail-on-missing
```
This exits with status `2` when at least one required section is missing, and `0` otherwise.

## Sample Output

```markdown
# 🩺 README Doctor — Documentation Quality Report
**Target File:** `sample-project/README.md`
**Documentation Health Score:** **65 / 100**
**Word Count:** 185 words | **Code Blocks:** 2

## 📋 Core Section Checklist
- **Prerequisites:** ✅ Present
- **Installation:** ✅ Present
- **Configuration:** ❌ Missing
- **Usage:** ✅ Present
- **Troubleshooting:** ❌ Missing

## 🤖 AI Documentation Review
### 1. Executive Summary
The README clearly explains what the tool does and how to install it, but lacks environment configuration details and troubleshooting guidance for first-time contributors.

### 2. Specific Actionable Improvements
- Add a **Configuration** section documenting the required `.env` variables.
- Include expected terminal output under the **Usage** section so users can verify success.
- Add a **Troubleshooting** section covering missing API key errors.
```

## Troubleshooting & Known Limitations
- **`GEMINI_API_KEY not found` Warning:** Ensure you have created a `.env` file inside `tools/readme-doctor/` or exported `GEMINI_API_KEY` in your terminal session (`export GEMINI_API_KEY="your_key"`).
- **Large Files:** To minimize token usage and latency, README files exceeding 12,000 characters are truncated before being sent to the LLM (static analysis still scans the entire file).
- **Non-Standard Headings:** Static checks inspect Markdown headings for common English section names. Unusual heading names may be reported as missing even if the content is present; the AI review can still identify the relevant content.
