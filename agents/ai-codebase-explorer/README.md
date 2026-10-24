# AI Codebase Explorer

> A read-only CLI agent that searches local source files and optionally uses an OpenAI model to explain retrieved evidence.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Developers joining an unfamiliar repository spend significant time hunting for where a concept, pattern, or feature is implemented. Standard `grep` lacks ranking and context; IDE search requires a full IDE setup.
- **Intended Users**: Software developers, code reviewers, and open-source contributors who need to quickly understand an unfamiliar local codebase.

### Key Features
- Searches common source-code and documentation file types across a local repository.
- Returns repository-relative paths, line numbers, and surrounding context lines.
- Ranks results by keyword relevance score.
- Optional LLM explanation mode (`--ai`) grounded strictly in retrieved snippets.
- Read-only: never executes or modifies repository code.
- Excludes common generated directories and credential filenames automatically.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: Vanilla Python script (no agent framework)
- **Models**: OpenAI `gpt-4.1-mini` (default, configurable via `OPENAI_MODEL`)
- **External APIs / Tools**: OpenAI Responses API (only when `--ai` flag is used)

---

## Architecture & Data Flow

```
[User CLI Input] --> [Keyword Extraction] --> [Repository Walker]
                                                      |
                                              [File Scanner & Scorer]
                                                      |
                                          [Ranked Snippet Results]
                                                      |
                            (--ai flag?) --> [OpenAI Responses API]
                                                      |
                                          [Explanation grounded in snippets]
```

The agent walks the target directory, skips generated folders and symlinks, scores each line by keyword hits, deduplicates overlapping snippets, and optionally sends the bounded evidence to an OpenAI model for explanation.

---

## Prerequisites

- Python 3.10 or newer
- `pip` package manager
- An OpenAI API key (only required for `--ai` mode)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/ai-codebase-explorer
   ```

2. **Set up virtual environment and install dependencies:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables (only for `--ai` mode):**
   ```bash
   export OPENAI_API_KEY="your-api-key"
   export OPENAI_MODEL="gpt-4.1-mini"   # optional, this is the default
   ```

---

## Configuration & Environment Variables

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `OPENAI_API_KEY` | Only for `--ai` | None | OpenAI API key for LLM explanations |
| `OPENAI_MODEL` | No | `gpt-4.1-mini` | OpenAI model identifier |

The application reads these directly from the shell environment. It does not auto-load `.env` files.

---

## How to Run

**Search-only mode (no API key required):**
```bash
python agent.py --repo /path/to/your/repository \
  --question "Where is authentication validated?"
```

**With AI explanation (`--ai` flag):**
```bash
python agent.py --repo /path/to/your/repository \
  --question "How does authentication work?" --ai
```

**Limit number of returned snippets:**
```bash
python agent.py --repo /path/to/your/repository \
  --question "database connection" --max-results 5
```

---

## Example Input & Output

### Example Input
```bash
python agent.py --repo . --question "how does search work"
```

### Example Output
```
Retrieved source evidence:

--- agent.py:85 (score: 1) ---
83: 
84: 
85: def search_code(root: Path, question: str, max_results: int = MAX_RESULTS) -> list[dict[str, Any]]:
86:     """Return ranked source snippets with repository-relative paths and line numbers."""
87:     root = root.expanduser().resolve()

--- README.md:74 (score: 1) ---
72: The tests use temporary sample files and do not require API credentials or network access.
73: 
74: ## How it works
75: 
76: 1. Walk the chosen directory while skipping common generated folders and symlinks.
```

---

## How to Test

```bash
python -m unittest discover -s tests -v
```

All 5 tests use temporary files and do not require API credentials or network access.

Expected output:
```
test_empty_query_returns_no_results ... ok
test_ignored_directories_are_not_scanned ... ok
test_invalid_repository_path_raises ... ok
test_search_returns_repo_relative_path_and_line ... ok
test_sensitive_files_are_excluded ... ok

Ran 5 tests in 0.00Xs

OK
```

---

## Known Limitations

- Retrieval is keyword-based, not semantic. It may miss relevant code that uses different terminology.
- The agent only sees retrieved snippets, not the full program's runtime behavior.
- `.gitignore` rules are not currently interpreted.
- Language support is based on file extensions, not full syntax parsing.
- Tested on Linux and macOS; Windows support is untested.
- Rate limits on free-tier OpenAI accounts will cause `--ai` mode to fail.

---

## Security & Privacy Considerations

- **Secrets Handling**: `OPENAI_API_KEY` is read from the shell environment only. `.env` files are gitignored and never committed.
- **Data Privacy**: In `--ai` mode, retrieved source snippets are sent to the OpenAI API. Do not use `--ai` on confidential or restricted source code unless your organization's policy permits it.
- **Safety**: The agent does not execute any code from the target repository and does not modify any files. It is strictly read-only.
- **Prompt Injection**: Source files may contain prompt-injection text. The model is instructed to treat retrieved content as untrusted data, but prompt instructions alone are not a security boundary.
- **Scope**: Only use this tool on repositories you are authorized to access.
- Common sensitive filenames (`.env`, `credentials.json`, private keys) and key/certificate extensions are excluded from scanning, but this is not a complete secret scanner.

---

## Future Improvements

- [ ] Support semantic search using embeddings for better retrieval relevance.
- [ ] Interpret `.gitignore` rules during the repository walk.
- [ ] Support local models via Ollama for air-gapped environments.
- [ ] Add streaming output for large AI responses.
- [ ] Support additional model providers (Anthropic, Gemini).

---

## License

This project is contributed under the repository's open-source license.
