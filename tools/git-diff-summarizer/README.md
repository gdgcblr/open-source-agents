# Git Diff Summarizer

> A lightweight CLI tool that inspects your Git diff and generates structured summaries, key file changes, and suggested pull request descriptions using Google Gemini.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Writing concise code summaries and clear pull request descriptions can be tedious and prone to missing key details when reviewing local diffs before creating a PR or requesting review.
- **Intended Users**: Software developers, open-source contributors, and code reviewers looking for a fast, terminal-native assistant to summarize uncommitted code changes.

### Key Features
- **Git Diff Observation**: Safely inspects unstaged tracked changes (or staged changes with `--staged`) using non-destructive Git commands.
- **Gemini-Powered Analysis**: Leverages Google Gemini models (e.g., `gemini-2.5-flash`) through the official `@google/genai` SDK to extract intent and highlight key modifications.
- **Pull Request Drafts**: Generates conventional-commit style PR titles, structured summaries, and recommended testing notes ready for GitHub/GitLab PR descriptions.
- **Markdown File Export**: Option to save reports directly to a Markdown file with `--output <path>`.
- **Safety Safeguards**: Read-only Git operations, diff payload size boundaries (100 KB limit), zero secrets in logs, and clear error diagnostics.

---

## Technical Stack

- **Language & Runtime**: Node.js (>= 18.0.0, tested on Node v26) & TypeScript 5.7+
- **Agent Architecture**: Lightweight 3-step sequential workflow (`Observe` ➔ `Analyze` ➔ `Report`)
- **Model Provider & SDK**: Google Gemini via `@google/genai` (default: `gemini-2.5-flash`)
- **Process & Config**: Node.js `child_process.execFile` (safe parameter arrays) and `dotenv`

---

## Architecture & Data Flow

```
+-------------------------------------------------------------+
|                     git-diff-summarizer                     |
+-------------------------------------------------------------+
       |
       | 1. Observe
       v
[Git Repository] ---> git diff --stat & git diff (safe read-only execFile)
       |
       | 2. Analyze (Diff & Stat payload)
       v
[Google Gemini API] (`@google/genai` model: gemini-2.5-flash)
       |
       | 3. Report
       v
[Terminal Output] & [Optional Markdown File (--output summary.md)]
```

The tool follows a simple, non-autonomous 3-step sequential agent pattern:
1. **Observe**: Safely checks the repository state and extracts file statistics and diff contents.
2. **Analyze**: Packages the changes into a focused prompt and invokes the Gemini model via `@google/genai`.
3. **Report**: Formats the model's structured response into readable Markdown and outputs to stdout or saves to a target file.

---

## Prerequisites

- **Node.js**: Version 18.0.0 or higher.
- **npm**: Version 8.0.0 or higher.
- **Git**: Installed and accessible in your system `PATH`.
- **Google Gemini API Key**: A valid API key obtained from [Google AI Studio](https://aistudio.google.com/).

---

## Installation & Setup

1. **Navigate to the tool directory:**
   ```bash
   cd tools/git-diff-summarizer
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Build TypeScript source:**
   ```bash
   npm run build
   ```

4. **Configure Environment Variables:**
   Copy the example environment configuration:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and set your `GEMINI_API_KEY`:
   ```bash
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes | *None* | Google Gemini API key from Google AI Studio |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Gemini model to use for diff analysis |

---

## How to Run

### Command-line Options

```text
Options:
  -r, --repo <path>     Path to the Git repository to inspect (default: current working directory)
  -o, --output <file>   Save the generated Markdown summary to a file
  -m, --model <name>    Gemini model to use (default: gemini-2.5-flash or GEMINI_MODEL env var)
      --staged          Inspect staged changes instead of unstaged tracked changes
  -h, --help            Show help message and exit
```

### Usage Examples

1. **Inspect current directory:**
   ```bash
   npm run start
   ```

2. **Inspect a specific repository:**
   ```bash
   npm run start -- --repo /path/to/another/repo
   ```

3. **Save summary to a Markdown file:**
   ```bash
   npm run start -- --output pr-summary.md
   ```

4. **Inspect staged changes with a different Gemini model:**
   ```bash
   npm run start -- --staged --model gemini-2.5-pro
   ```

5. **Display help and CLI flags:**
   ```bash
   npm run start -- --help
   ```

---

## Example Input & Output

### Example Input
Unstaged changes in a repository modifying `src/auth.ts`:

```bash
npm run start
```

### Example Terminal Output

```text
🔍 [Observe] Inspecting Git changes in: /Users/dev/projects/web-app
📊 Found changes in repository:
 src/auth.ts | 14 +++++++++++---
 1 file changed, 11 insertions(+), 3 deletions(-)

🤖 [Analyze] Sending diff (482 bytes) to Gemini (gemini-2.5-flash)...
   (Note: Code diff is sent to Google Gemini API for analysis)

=================== SUMMARY REPORT ===================

# Git Diff Summary

*Generated by `git-diff-summarizer` using gemini-2.5-flash*
*Repository: `/Users/dev/projects/web-app`*

---

## Summary of Changes
Updated token refresh handling in `auth.ts` to retry expired sessions with exponential backoff and sanitize error logging when authentication fails.

## Key Changed Files
- `src/auth.ts`: Added token renewal retry logic and removed raw error token logging to prevent accidental credential leakage.

## Suggested Pull Request Description
- **Title**: `fix(auth): add exponential backoff to token refresh and sanitize logs`
- **Description**:
  - Implements retry mechanism for expired authentication tokens with jitter.
  - Sanitizes authentication error objects before passing to logger.
- **Testing Notes**:
  - Run `npm test` on auth test suite.
  - Test expired JWT renewal flow with simulated network failure.

======================================================
```

---

## How to Test

Run the automated test suite using Node's native test runner:

```bash
# Run full build and test suite
npm test

# Run TypeScript type check
npm run typecheck
```

The test suite validates:
- CLI argument parsing (`--help`, `--repo`, `--output`, `--model`, `--staged`, error handling).
- Git repository status checks, clean repository detection (`hasChanges: false`), and invalid directory path errors.
- Mock Gemini API integration and error handling (missing API key, quota exhaustion, invalid credentials).

---

## Known Limitations

- **Tracked Files Only**: In accordance with `git diff`, only modified tracked files are inspected. Newly created untracked files are not visible until tracked with `git add -N` or staged.
- **Diff Size Limits**: For safety and token economy, diffs exceeding 100 KB are blocked with a recommendation to summarize smaller sets of changes.
- **Internet Connection Required**: Calls the Google Gemini API over HTTPS; offline analysis is not supported.

---

## Security & Privacy Considerations

- **Third-Party Data Transmission**: Source code diffs are transmitted over HTTPS to Google's Gemini API endpoints for analysis when the user invokes the command with a configured `GEMINI_API_KEY`.
- **Zero Secrets Policy**: API keys are loaded strictly through environment variables or local `.env` files (which are ignored in `.gitignore`). No keys or raw diffs are logged to disk or console.
- **Safe Execution**: All external commands use `child_process.execFile` with explicit argument arrays—never string concatenation or shell interpolation.
- **Read-Only Operations**: The tool strictly runs read-only commands (`git diff`, `git diff --stat`, `git rev-parse`). It will never modify, stage, commit, or push repository code.

---

## Future Improvements

- [ ] Support diffing specific branches or commit ranges (e.g., `--compare main..feature`).
- [ ] Add interactive prompt to refine the generated PR description.
- [ ] Support local LLM backends (such as Ollama) for completely offline workflows.

---

## License

This project is contributed under the repository's open-source Apache-2.0 license.
