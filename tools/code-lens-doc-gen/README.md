# CodeLens Doc Gen

> Automatically scan a codebase, analyze its structure in depth, and generate categorized documentation (User Docs & Dev Docs) using Google Gemini — with incremental updates on every code change.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Maintaining up-to-date documentation is one of the most neglected tasks in software development. When code changes, docs go stale. Teams end up with outdated READMEs, missing API references, and no clear separation between user-facing and developer-facing documentation.
- **Intended Users**: Development teams, open-source maintainers, and individual developers who want their documentation to stay in sync with their codebase automatically.

### Key Features
- **Deep Codebase Scanning**: Recursively walks the entire file tree, detecting languages, reading contents, and respecting `.gitignore` patterns and size limits.
- **AST-Powered Analysis**: Uses Python's `ast` module for thorough structural extraction (classes, functions, args, docstrings, decorators, visibility). Falls back to regex-based heuristics for JavaScript, TypeScript, Go, Java, and other languages.
- **Intelligent Categorization**: Uses Google Gemini to classify every file and component as User Docs, Dev Docs, or Both — with a rule-based fallback for offline usage.
- **Separated Documentation Output**: Generates two distinct documentation sets:
  - `user-docs/` — Installation, configuration, usage, API reference
  - `dev-docs/` — Architecture, module internals, data flow, extension guide
- **Incremental Updates**: Detects code changes via `git diff`, re-analyzes only affected files, and updates documentation without full regeneration.
- **Offline Mode**: Can generate documentation using rule-based categorization without any LLM calls.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **LLM Provider**: Google Gemini (via `google-generativeai` SDK)
- **CLI Framework**: Click
- **Terminal UI**: Rich (progress bars, tables, colored output)
- **Static Analysis**: Python `ast` module (built-in), regex for other languages
- **VCS Integration**: Git (via subprocess — no external git library)

---

## Architecture & Data Flow

```
[User runs CLI command]
        │
        ▼
┌──────────────────┐     ┌──────────────────┐
│  Scanner          │     │  Diff Analyzer    │
│  (scanner.py)     │     │  (diff_analyzer)  │
│  Walks file tree  │     │  git diff parsing │
└────────┬─────────┘     └────────┬─────────┘
         │                        │
         ▼                        ▼
┌──────────────────┐     (used by 'update' command)
│  Analyzer         │
│  (analyzer.py)    │
│  AST + regex      │
│  extraction       │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Categorizer      │
│  (categorizer.py) │
│  Gemini LLM call  │
│  or rule-based    │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Generator        │
│  (generator.py)   │
│  Gemini LLM call  │
│  Markdown output  │
└────────┬─────────┘
         │
    ┌────┴────┐
    ▼         ▼
user-docs/  dev-docs/
```

---

## Prerequisites

Before running this project, ensure you have:
- **Python 3.10+** installed
- **pip** (Python package manager)
- **Git** (for the `update` command — optional for `scan` and `generate`)
- **Google Gemini API key** (free tier available — see setup below)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/code-lens-doc-gen
   ```

2. **Set up a virtual environment and install dependencies:**
   ```bash
   python -m venv .venv

   # Windows:
   .venv\Scripts\activate

   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Configure your API key:**
   ```bash
   # Copy the example env file
   cp .env.example .env
   ```

   Then edit `.env` and replace `your_gemini_api_key_here` with your actual key.

   **Where to get the API key:**
   - Go to [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
   - Sign in with your Google account
   - Click "Create API Key"
   - Copy the key and paste it into your `.env` file

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes | *None* | Your Google Gemini API key |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Gemini model to use |
| `OUTPUT_DIR` | No | `./docs_output` | Output directory for generated docs |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `MAX_FILE_SIZE` | No | `524288` | Maximum file size in bytes to analyze (default: 512KB) |

---

## How to Run

### Scan a codebase (no LLM calls, local only)
```bash
# Scan current directory
python main.py scan .

# Scan with verbose output (shows classes, functions, etc.)
python main.py scan /path/to/project --verbose
```

### Generate full documentation
```bash
# Generate docs for current directory
python main.py generate .

# Specify output directory
python main.py generate /path/to/project --output ./my-docs

# Offline mode (no Gemini API needed — uses rule-based categorization)
python main.py generate . --offline
```

### Update docs after code changes
```bash
# Update based on last commit
python main.py update .

# Update based on specific git range
python main.py update . --base HEAD~5 --head HEAD

# Update with custom output
python main.py update . --output ./my-docs --base main --head feature-branch
```

### View Documentation in Interactive Web UI
```bash
# Launch the built-in web portal (opens http://localhost:8000 automatically)
python main.py serve

# Specify custom port or directory
python main.py serve --port 3000 --dir ./my-docs
```

---

## Example Input & Output

### Example Input
```bash
python main.py generate /path/to/my-python-project
```

### Example Output
```
╭──────────────────── CodeLens Generator ────────────────────╮
│ Generating documentation for: /path/to/my-python-project   │
│ Output directory: ./docs_output                             │
│ LLM Model: gemini-2.0-flash                                │
│ Mode: Online (Gemini)                                       │
╰────────────────────────────────────────────────────────────╯

Step 1/4: Scanning codebase...
       Scan Summary
┌───────────────┬───────┐
│ Metric        │ Value │
├───────────────┼───────┤
│ Total files   │ 24    │
│ Total lines   │ 3,847 │
│ Skipped files │ 2     │
└───────────────┴───────┘

Step 2/4: Analyzing code structure...
  Found 8 classes and 34 functions

Step 3/4: Categorizing components...
  📄 User docs: 7 files
  🔧 Dev docs:  12 files
  📋 Both:      5 files

Step 4/4: Generating documentation...

╭────────────────────── ✅ Complete ──────────────────────╮
│ Documentation generated successfully!                    │
│                                                          │
│ 📁 Output: /path/to/my-python-project/docs_output        │
│ 📄 Files written: 5                                      │
│                                                          │
│ User docs: ./docs_output/user-docs/                      │
│ Dev docs:  ./docs_output/dev-docs/                       │
╰──────────────────────────────────────────────────────────╯
```

Generated output structure:
```
docs_output/
├── user-docs/
│   ├── index.md
│   └── user-guide.md
├── dev-docs/
│   ├── index.md
│   └── developer-guide.md
└── .codelens-state.json
```

---

## How to Test

```bash
# Install test dependency
pip install pytest

# Run the test suite (no API key needed — tests are local-only)
pytest tests/ -v
```

The tests cover:
- Configuration loading and validation
- Codebase scanning (file tree walking, language detection, ignore patterns)
- Python AST analysis (classes, functions, docstrings, visibility)
- Config file key extraction
- LLM content condensation

---

## Known Limitations

- **Python gets the deepest analysis**: Python files are analyzed via full AST parsing. JavaScript, TypeScript, Go, and Java use regex-based extraction which may miss edge cases (e.g., dynamically defined functions).
- **Large codebases**: Files exceeding 512KB (configurable) are skipped. Very large projects may hit Gemini token limits — the tool truncates analysis data to stay within bounds.
- **Gemini rate limits**: Free-tier Gemini API has rate limits. If you hit them, the tool retries with exponential backoff (up to 3 retries).
- **Git required for updates**: The `update` command requires git. Use `generate` for non-git projects.
- **Single-language docstrings**: Docstring extraction only works for Python. Other languages use general regex patterns.
- **No conversation memory**: Each run is independent. The tool doesn't maintain context between separate invocations beyond the `.codelens-state.json` metadata.

---

## Security & Privacy Considerations

- **Secrets Handling**: API keys are loaded exclusively from the `.env` file (never hardcoded). The `.env` file is in `.gitignore` and is never committed.
- **Data Privacy**: The tool sends condensed codebase summaries (file paths, class/function names, docstrings) to the Google Gemini API for categorization and documentation generation. Actual file contents are NOT sent in full — only structural metadata. If this is a concern, use `--offline` mode.
- **Safety**: The tool performs read-only operations on your codebase. It does not execute any code, modify source files, or run arbitrary commands. It only writes to the output directory.

---

## Future Improvements

- [ ] Support tree-sitter for accurate multi-language AST parsing
- [ ] Add watch mode (file system watcher for live doc updates during development)
- [ ] GitHub Actions workflow template for CI/CD auto-update
- [ ] Support local models via Ollama (fully offline doc generation with LLM)
- [ ] Configurable documentation templates (custom sections, branding)
- [ ] Diff-aware partial regeneration (update only changed sections, not entire docs)

---

## License

*This project is contributed under the repository's open-source license.*
