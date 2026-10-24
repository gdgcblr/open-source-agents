# changelog-generator

> An automated, AI-assisted changelog generator that groups Conventional Commits into structured release notes and synthesizes executive release summaries using Gemini.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Writing release notes and maintaining a readable `CHANGELOG.md` across fast-moving repositories is repetitive and often skipped or delayed during release cycles.
- **Intended Users**: Open-source maintainers, software release engineers, and development teams practicing semantic versioning and Conventional Commits.

### Key Features
- **Deterministic Conventional Commit Parsing**: Automatically groups commits into standard categories:
  - ⚠️ Breaking Changes (`BREAKING CHANGE` or `!`)
  - 🚀 Features & Enhancements (`feat`)
  - 🐛 Bug Fixes (`fix`)
  - ⚡ Performance Improvements (`perf`)
  - 🔨 Refactoring & Code Quality (`refactor`)
  - 📚 Documentation (`docs`)
  - 🧹 Maintenance & Chores (`chore`)
- **AI Executive Summary Synthesis (`--ai`)**: Uses Gemini 2.0 Flash to analyze the change set and generate a concise 2-4 sentence executive overview for human readers.
- **Flexible Git Range Detection**: Automatically targets latest tags or custom ranges (`--from-tag v1.0 --to-tag v1.1`).
- **Direct File Output**: Can print to stdout (perfect for GitHub Actions release jobs) or write directly to a `CHANGELOG.md` file (`-o`).

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Model Provider**: Google Gemini API via `google-genai` (optional, for `--ai` synthesis)
- **External Dependencies**: Zero required for core parsing; `google-genai` for optional AI synthesis

---

## Prerequisites

- Python 3.10+
- `git` installed and available in `PATH`
- *(Optional for `--ai`)*: Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey)

---

## Installation & Setup

1. **Navigate to project directory:**
   ```bash
   cd tools/changelog-generator
   ```

2. **Install dependencies (optional for AI mode):**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure API key (optional for AI mode):**
   ```bash
   cp .env.example .env
   # Set GEMINI_API_KEY=<your key> in .env
   ```

---

## CLI Options & Usage

```bash
# Generate changelog from latest tag to HEAD
python main.py

# Generate changelog between specific tags
python main.py --from-tag v1.0.0 --to-tag v1.1.0 --title "Version 1.1.0"

# Synthesize release highlights using Gemini
python main.py --ai

# Write directly to CHANGELOG.md
python main.py --output CHANGELOG.md
```

---

## Example Output

```markdown
## v1.1.0 (2026-10-24)

### 💡 Release Highlights
This release introduces a new offline fallback engine for commit analysis along with
native Git hook automation, improving developer workflow security and speed.

### 🚀 Features & Enhancements

- **agents:** add git-commit-agent with Google ADK and Conventional Commits (`c84ec28`)

### 🐛 Bug Fixes

- **auth:** resolve token expiry calculation edge cases (`a1b2c3d`)
```

---

## How to Test

Run the automated test suite:
```bash
python -m unittest discover -s tests
```

---

## License

*Contributed under the project's open-source license.*
