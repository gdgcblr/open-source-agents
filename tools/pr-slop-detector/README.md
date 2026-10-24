# PR Slop Detector

> Scores GitHub pull requests for low-effort "AI slop" and explains why, with file-and-line evidence, so maintainers can triage drive-by PRs in seconds instead of minutes.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Coding assistants make it cheap to open plausible-looking PRs that the author never read: hallucinated imports, stub functions presented as finished, comments that restate code, marketing-style descriptions, and pasted "Certainly! Here's the updated code". Each one costs a maintainer real review time, and events like Hacktoberfest multiply them.
- **Intended Users**: Open-source maintainers and repo admins, especially of community repos like this one that accept contributions from first-time contributors.

### Key Features
- **Deterministic heuristics (no API key needed)**: 14 explainable checks (17 signal types) across the description, the diff, and the author context, each with a weight and concrete evidence.
- **Local Gemma reviewer built on Google ADK**: by default it runs Google's open-weights **Gemma 4** locally through **Ollama**, so you need no API key, pay nothing, and no code leaves your machine. Hosted Gemini is one flag away (`--provider gemini`). The agent treats the heuristics as leads, opens the diffs it finds suspicious through tools, and returns a structured verdict with verbatim evidence, strengths, and questions for the author.
- **Questions only the real author can answer**: specific one-line questions that someone who understands the change answers easily, and someone who pasted LLM output can't.
- **CI-ready**: posts (and on re-runs, edits) one PR comment, can add a label, and can fail a check. A safe GitHub Actions workflow is included.
- **Judges the work, not the tool**: AI-assisted PRs that are correct and focused score low. Disclosing AI use (for example a `Co-Authored-By` line) is never penalized.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+
- **Agent Framework / Core Library**: Google Agent Development Kit (`google-adk` 2.13+), with LiteLLM as ADK's adapter to Ollama
- **Models**: Gemma 4 via Ollama (`gemma4:e2b-it-qat` by default; `e4b` / `12b` on bigger machines), or hosted Gemini (`gemini-3.5-flash`) as an option
- **External APIs / Tools**: Ollama (local), GitHub REST API (via `httpx`), Pydantic for structured output

---

## Architecture & Data Flow

See [ARCHITECTURE.md](ARCHITECTURE.md) for the component diagram, data flow, model backends, and output behavior.

### Heuristic signals

| Signal | What it catches |
| :--- | :--- |
| `assistant-leakage` | "As an AI", "I hope this helps", "Certainly!", "Here's the updated…" in the description, commits, or code |
| `llm-phrasing` | High density of stock LLM vocabulary ("delve", "seamless", "robust", "plays a crucial role") |
| `emoji-headings` | 🚀 ✨ ✅ decorated section headings |
| `description-inflation` | Description wildly larger than the diff |
| `unverified-claims` | "All tests pass" / "thoroughly tested" with no test file changes |
| `placeholder-code` | `TODO: implement`, `your_api_key_here`, `# add your logic here`, `NotImplementedError` (ignored in docs and `.env.example`) |
| `undeclared-imports` | Python/JS imports that no manifest declares and that aren't local modules: hallucinated or missing dependencies |
| `restating-comments` / `comment-density` | `# Initialize the result variable` → `result = None` |
| `ai-artifact-files` | Committed `IMPLEMENTATION_SUMMARY.md`, `.aider.chat.history.md`, `.cursor/`… |
| `whitespace-churn` | Files whose only change is formatting |
| `scope-sprawl` | Many files across many unrelated top-level directories |
| `blanket-error-handling` | `except Exception:` wrapped around everything |
| `single-dump-commit` / `generic-commits` | One "Update api.py" commit adding hundreds of lines |
| `new-account` | Account < 30 days old making a first contribution |
| `pr-spray` | Author opened ≥15 PRs across ≥8 repos in the last 14 days |

Bot accounts (`*[bot]`) skip the author and template checks. No single signal can flag a PR on its own.

---

## Prerequisites

- Python 3.11+
- `pip` (or `uv`)
- [Ollama](https://ollama.com/download) with a Gemma 4 model pulled, for the LLM review:
  ```bash
  ollama pull gemma4:e2b-it-qat    # 4.3 GB, smallest Gemma 4 with tool calling; fits in 8 GB RAM
  # Note: plain `gemma4:e2b` resolves to a 7.5 GB MLX build on Apple Silicon
  # 16 GB+ RAM: ollama pull gemma4:e4b  (better reviews)
  ```
  `--no-llm` skips the LLM entirely. Alternatively, use `--provider gemini` with a [Google AI Studio](https://aistudio.google.com/apikey) key; no Google Cloud project setup is needed.
- A GitHub token: optional for reading public PRs (raises the rate limit from 60/hour), required for `--post-comment` / `--label`

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/pr-slop-detector
   ```

2. **Create a virtual environment and install dependencies** (includes `litellm`, ADK's adapter for Ollama):
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # then edit .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `LLM_PROVIDER` | No | `ollama` | `ollama` (local Gemma) or `gemini` (hosted) |
| `MODEL_NAME` | No | `gemma4:e2b-it-qat` / `gemini-3.5-flash` | Model for the chosen provider |
| `OLLAMA_API_BASE` | No | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_NUM_CTX` | No | `16384` | Context window for the local model; raise it if you have the RAM |
| `MAX_PATCH_CHARS` | No | `4000` / `12000` | Diff characters the agent sees per file (Ollama / Gemini) |
| `GOOGLE_API_KEY` | Only for `gemini` | *None* | Gemini API key (`GEMINI_API_KEY` also works) |
| `GITHUB_TOKEN` | For commenting/labeling | *None* | GitHub token; needs `pull-requests: write` / `issues: write` to post |
| `SLOP_THRESHOLD` | No | `60` | Score at or above which a PR is flagged 🔴; scores ≥ 45% of it are 🟡 |

---

## How to Run

```bash
# Full review (heuristics + local Gemma 4 agent) of a public PR
python -m slop_detector owner/repo#123
python -m slop_detector https://github.com/owner/repo/pull/123

# Hosted Gemini instead of local Gemma
python -m slop_detector owner/repo#123 --provider gemini

# Bigger local model
python -m slop_detector owner/repo#123 --model gemma4:e4b

# Heuristics only: instant, no model at all
python -m slop_detector owner/repo#123 --no-llm

# Review a local branch before opening the PR
git diff main...HEAD > /tmp/my.diff
python -m slop_detector --patch /tmp/my.diff --title "My PR title" --body-file pr_body.md

# Save a PR once, re-run offline (reproducible demos, tuning)
python -m slop_detector owner/repo#123 --save-json pr.json --no-llm
python -m slop_detector --from-json pr.json

# CI: comment on the PR, label it if flagged, fail the check if flagged
python -m slop_detector owner/repo#123 --post-comment --label possible-ai-slop --fail-on-slop

# Machine-readable output
python -m slop_detector owner/repo#123 --format json
```

**Interactive mode with the ADK dev UI:** from this directory, run `adk web`, pick `slop_detector`, and ask *"Review owner/repo#123"*. The agent loads the PR with its `load_pull_request` tool and you can follow up ("why did you flag api.py?").

**As a GitHub Action:** copy [`examples/pr-slop-check.yml`](examples/pr-slop-check.yml) to `.github/workflows/`. By default it installs Ollama on the runner and caches the Gemma model, so you don't need any secrets. Expect a few minutes per PR on CPU-only runners; the file shows how to switch to Gemini for faster runs. The workflow never checks out or executes PR code. See the comments in the file.

---

## Example Input & Output

### Example Input
```bash
python -m slop_detector --from-json tests/fixtures/slop_pr.json --no-llm
```
`tests/fixtures/slop_pr.json` is a **synthetic** PR built to show off the signals (emoji-heavy description, stub functions, a hallucinated `fastjsonschema` import, a committed `IMPLEMENTATION_SUMMARY.md`).

### Example Output
Real output from the command above (trimmed to the first rows of the table):
```
## PR Slop Check: 🔴 Likely AI slop (score 100/100)

**example-org/user-service#101** · 4 files · +61 / -4 · by @drive-by-dev

> Heuristics-only run (no LLM review).

| Signal | Weight | Evidence |
| :--- | ---: | :--- |
| Chat-assistant text pasted verbatim | +30 | PR description: "I hope this helps"<br>IMPLEMENTATION_SUMMARY.md: "Certainly!" ... |
| Description is dense with stock LLM phrasing | +20 | 19 hits in 117 words (16.2/100 words): "best practices", "comprehensive", ... |
| Placeholder or unfinished code | +18 | user_service/api.py:15 `your_api_key_here`<br>user_service/api.py:24 `TODO: implement` ... |
| Comments that restate the next line of code | +15 | user_service/api.py:1 `Import the os module` → `import os` ... |
| Imports packages no manifest declares (hallucinated or missing deps) | +14 | user_service/api.py:6 imports `fastjsonschema`, not declared in any manifest ... |
| Author is spraying PRs across many repositories | +12 | @drive-by-dev opened 42 PRs across ≥31 repos recently |
...
```
The matching clean fixture (`tests/fixtures/clean_pr.json`) scores **0/100 🟢**.

With the LLM enabled, the report also gets an LLM summary, a **Findings** list (each with a severity), **Strengths**, and **Questions for the author**, plus a verdict blended from both scores.

**Guardrails on the model's output:**
- A finding's quoted evidence is shown only if it really occurs in the PR (ignoring whitespace and case). Bare file names don't count.
- If none of the model's findings quote real PR text, its score is weighted 0.3 instead of 0.65, and the report says so.
- Lockfiles and generated files are hidden from the agent, and a diff that GitHub omitted is reported to the agent as normal, not suspicious.

**Live runs with local Gemma 4** (`gemma4:e2b-it-qat`, Apple M2, 8 GB RAM, Oct 2026):

| PR | Heuristics | Gemma | Final | Time |
| :--- | ---: | ---: | :--- | ---: |
| Synthetic slop fixture | 100 | 85 (no verifiable quotes, down-weighted) | 🔴 96 | 16.7 min* |
| Synthetic clean fixture | 0 | 15 | 🟢 10 | 2.4 min |
| `pallets/flask#6168`, real maintainer PR dropping Python 3.10 | 0 | 20 / 26 | 🟢 13 / 🟢 8 (two runs) | 2.8 / 4.0 min |

Model scores vary a little between runs; the verdicts were stable. \*The Mac was swapping heavily during this run. An earlier run of the same fixture took 4.2 minutes and scored 🔴 77.

`pallets/flask#6168` first scored 🟡 55, a false positive: Gemma opened `uv.lock`, saw that GitHub had omitted the diff, and called it suspicious. That run is why lockfiles are now hidden from the agent, omitted diffs are labelled as normal, and unsupported LLM scores are down-weighted.

**Heuristics-only false-positive check:** 9 recently merged PRs from `pallets/flask`, `psf/requests`, and `google/adk-python` all scored 0-8 🟢.

---

## Sample Report

This is what the tool prints to the terminal, and what `--post-comment` posts on the PR (as a single comment that later runs edit in place). Both samples below are **unedited output from live runs** with the default local model (`gemma4:e2b-it-qat` via Ollama), rendered the way GitHub shows them.

### Parts of the report

| Part | What it tells the maintainer |
| :--- | :--- |
| **Header** | Verdict badge (🟢 Looks good / 🟡 Needs a closer human look / 🔴 Likely AI slop) and the final 0-100 score |
| **PR line** | Link, size (files, +/- lines), author |
| **Summary** | The model's two-or-three-sentence take (or a note that the run was heuristics-only, with the reason) |
| **ℹ️ Down-weight notice** | Shown when none of the model's findings quote text that really occurs in the PR, so its score counted for less |
| **Findings** | Each problem with severity and file; a quoted snippet appears **only if it was found verbatim in the PR** |
| **Strengths** | What the PR does well, so the report is not one-sided |
| **Questions for the author** | Specific questions a real author can answer in one line; useful to paste into the review |
| **Heuristic signals** (collapsed) | Every deterministic signal that fired, with its weight and file:line evidence |
| **Footer** | Threshold, plus a reminder that this is a triage aid and a maintainer decides |

### Sample 1: flagged PR (🔴)

Input: the synthetic fixture `tests/fixtures/slop_pr.json`, run with `python -m slop_detector --from-json tests/fixtures/slop_pr.json`. The heuristics alone scored 100. Gemma scored 85, but quoted nothing verifiable, so its score was down-weighted. The result was still 🔴 96. The small model's findings are reasonable, but it attributes the first one to the wrong files and leaves out quotes. That's why the report shows only evidence it can verify.

> ## PR Slop Check: 🔴 Likely AI slop (score 96/100)
>
> **example-org/user-service#101** · 4 files · +61 / -4 · by @drive-by-dev
>
> > This pull request exhibits several high-risk issues, including placeholder logic, unfinished TODOs, and the use of AI-generated artifacts, suggesting the implementation is not complete or functional. Significant concerns include undeclared imports and poor error handling via a blanket exception block. While the PR modifies core files, the lack of functional code and proper dependency management indicates a high risk of introducing bugs.
>
> > ℹ️ None of the model's findings quote text found in the PR, so its score (85) was down-weighted.
>
> ### Findings
>
> - **[Medium]** The PR description is heavily populated with generic, marketing-style LLM phrasing, suggesting the description was generated by an AI rather than written by a human. (`user_service/api.py, IMPLEMENTATION_SUMMARY.md`)
> - **[High]** The PR contains placeholder logic and unfinished TODOs presented as finished code, indicating the implementation is not complete or functional. (`user_service/api.py`)
> - **[High]** The author has committed files that appear to be scratch or assistant-generated artifacts, which is a strong indicator of AI-assisted work without proper human review. (`IMPLEMENTATION_SUMMARY.md`)
> - **[High]** The PR includes undeclared imports (e.g., `fastjsonschema`, `utils`) which suggests the dependencies are not properly managed or the code is hallucinating imports. (`user_service/api.py`)
> - **[Medium]** The PR uses a blanket `except Exception:` block, which masks potential bugs and indicates poor, non-specific error handling. (`user_service/api.py`)
> - **[Low]** The author is a brand-new account making their first contribution, which, combined with the high heuristic score, suggests a lack of established contribution patterns. (`Context`)
>
> ### Strengths
>
> - The PR modifies core files (`api.py`, `models.py`, `config.py`) and introduces new structure, suggesting an attempt at a significant refactor, even if the execution is flawed.
>
> ### Questions for the author
>
> 1. Why is the `fastjsonschema` library imported in `user_service/api.py` if it is not declared in the project's manifest or dependencies?
> 2. What specific error conditions is the blanket `except Exception:` block intended to catch, and how does this differ from specific exception handling?
> 3. The description claims "comprehensive error handling," but the implementation uses a generic catch-all; what is the specific, intended error flow for critical failures?
>
> <details><summary>Heuristic signals (score 100/100, 12 fired)</summary>
>
> | Signal | Weight | Evidence |
> | :--- | ---: | :--- |
> | Chat-assistant text pasted verbatim | +30 | PR description: "I hope this helps"<br>PR description: "Let me know if you'd like"<br>IMPLEMENTATION_SUMMARY.md: "Certainly!"<br>IMPLEMENTATION_SUMMARY.md: "Here's the updated" |
> | Description is dense with stock LLM phrasing | +20 | 19 hits in 117 words (16.2/100 words): "best practices", "comprehensive", "elevates", "enhance the overall maintainability", "enhanced readability", "fosters", "furthermore", "holistic" |
> | Placeholder or unfinished code | +18 | user_service/api.py:15 `your_api_key_here`<br>user_service/api.py:24 `TODO: implement`<br>user_service/api.py:31 `# Add your logic here`<br>user_service/api.py:32 `raise NotImplementedError` |
> | Comments that restate the next line of code | +15 | user_service/api.py:1 `Import the os module` → `import os`<br>user_service/api.py:3 `Import the requests library` → `import requests`<br>user_service/api.py:5 `Import the fastjsonschema validator` → `import fastjsonschema`<br>user_service/api.py:11 `Initialize the result variable` → `result = None`<br>user_service/api.py:14 `Call the API to get the user` → `result = requests.get(f"https://example.com/api/u…` |
> | Imports packages no manifest declares (hallucinated or missing deps) | +14 | user_service/api.py:6 imports `fastjsonschema`, not declared in any manifest<br>user_service/api.py:7 imports `utils`, not declared in any manifest |
> | Author is spraying PRs across many repositories | +12 | @drive-by-dev opened 42 PRs across ≥31 repos recently |
> | Committed assistant scratch files | +11 | IMPLEMENTATION_SUMMARY.md |
> | Claims testing that the diff does not show | +10 | "All tests pass", "thoroughly tested", yet no test files were added or changed |
> | Emoji-decorated section headings | +6 | ## 🚀 Overview<br>## ✨ Key Changes<br>## ✅ Testing<br>## 📝 Summary |
> | Files with whitespace/formatting-only changes | +6 | user_service/models.py<br>user_service/config.py |
> | Blanket try/except wrapped around everything | +6 | user_service/api.py:16 `except Exception as e:`<br>user_service/api.py:26 `except Exception:`<br>user_service/api.py:33 `except Exception:`<br>user_service/api.py:39 `except:` |
> | Brand-new account, first contribution | +5 | @drive-by-dev created 14 days ago, association FIRST_TIME_CONTRIBUTOR |
>
> </details>
>
> <sub>Flag threshold: 60. This is an automated triage aid, not a judgment of the contributor. AI-assisted work is welcome when it is correct, focused, and understood. A maintainer makes the final call.</sub>

### Sample 2: clean PR (🟢)

Input: a real merged maintainer PR, `python -m slop_detector pallets/flask#6168`. No heuristic signals fired. Gemma read the two relevant diffs, called the change targeted and functional, and asked sensible follow-up questions.

> ## PR Slop Check: 🟢 Looks good (score 8/100)
>
> **[pallets/flask#6168](https://github.com/pallets/flask/pull/6168)** · 12 files · +67 / -433 · by @davidism
>
> > This PR addresses the goal of dropping support for Python 3.10 by making minor compatibility adjustments to `super().convert` in `src/flask/cli.py` and refactoring the `app_signal` test in `tests/test_appctx.py`. The changes appear targeted and functional, focusing on necessary code paths and test cleanup.
>
> > ℹ️ None of the model's findings quote text found in the PR, so its score (26) was down-weighted.
>
> ### Findings
>
> - **[Low]** The PR modifies the `convert` method in `src/flask/cli.py` to adjust how `super().convert` is called in a list comprehension, which appears to be a minor compatibility adjustment. (`src/flask/cli.py`)
> - **[Low]** The PR refactors the `app_signal` test in `tests/test_appctx.py` by removing version-specific conditional logic and simplifying the assertion structure. (`tests/test_appctx.py`)
>
> ### Strengths
>
> - The PR is focused on the stated goal of dropping support for Python 3.10, addressing necessary code paths and test cleanup.
> - The changes appear targeted and functional, suggesting a human understanding of the codebase.
>
> ### Questions for the author
>
> 1. Why was the specific change to `super().convert` in `src/flask/cli.py` necessary for Python 3.10 compatibility?
> 2. What specific behavior in the original `app_signal` test necessitated the removal of the `sys.version_info >= (3, 11)` conditional block?
>
> <details><summary>Heuristic signals (score 0/100, 0 fired)</summary>
>
> No heuristic signals fired.
>
> </details>
>
> <sub>Flag threshold: 60. This is an automated triage aid, not a judgment of the contributor. AI-assisted work is welcome when it is correct, focused, and understood. A maintainer makes the final call.</sub>

---

## How to Test

```bash
pytest
```

The suite (26 tests) covers every heuristic against the synthetic slop/clean fixtures, guards against known false positives (placeholders in docs, declared/local imports, AI-disclosure lines, bots, lockfiles), the diff parser, score blending and evidence-gated scoring, evidence verification, the two-step ADK agent's tools and wiring, provider selection, and tolerant parsing of model output. **No network, Ollama, or API key is needed.**

Manual check against a live PR:
```bash
python -m slop_detector pallets/flask#6168 --no-llm   # expect 🟢
```

---

## Known Limitations

- **The small local model is a weak reviewer.** Gemma 4 E2B (about 2B effective parameters) catches the obvious problems and asks sensible questions, but it often quotes nothing verifiable, sometimes skips reading the diffs, and sometimes miscategorizes findings. The guardrails above limit the damage. For real use, `gemma4:e4b`/`12b` (16 GB+ RAM) or `--provider gemini` will review better. The hosted Gemini path is wired the same way but was only tested with a stubbed model.
- **Slow on 8 GB machines**: 2.5–4 minutes per PR normally, much longer under memory pressure. Close other apps or use `--no-llm` for instant results.
- **Heuristic weights are hand-tuned** on synthetic fixtures and a small sample of real PRs, not a labeled dataset. Expect false positives on non-native-English authors who write in a formal style, and on projects whose PR template uses emoji headings.
- **The import check** covers Python and JS/TS only, needs a manifest, and maps import names to package names with a small alias table (e.g. `yaml` → `pyyaml`). Unusual mappings can produce a false `undeclared-imports`.
- **Large PRs**: GitHub omits patches for very large files. The agent reads at most 4 diffs of 4k characters each with Gemma (8 × 12k with Gemini), so on big PRs it samples rather than reads everything.
- **The `pr-spray` signal** uses GitHub search, which is heavily rate-limited for anonymous calls. Without a token it is often silently skipped.
- Tested on macOS (Apple M2, 8 GB) with Python 3.12 and Ollama 0.40; Linux/Windows untested. The GitHub Action workflow has not been run on a real runner yet.

---

## Security & Privacy Considerations

- **Secrets Handling**: Keys are read from environment variables / `.env` (git-ignored). Nothing is logged or written to disk except when you pass `--save-json`, which writes PR content you requested.
- **Data Privacy**: With the default Ollama backend, everything stays on your machine (only the GitHub API is contacted to fetch the PR). With `--provider gemini`, the PR title, description, commit messages, file list, and up to 8 diffs are sent to Google's Gemini API.
- **Safety**: The tool never executes PR code. The provided workflow uses `pull_request_target` *only* because it never checks out the PR head. Don't add `ref: head.sha` to it. PR content is untrusted input to the LLM: a PR could contain text trying to talk the reviewer into a low score. The structured output and the independent heuristic score limit the damage, and the report is advisory: a maintainer makes the final call.
- **Fairness**: The output is a triage aid, not an accusation. The posted comment says so explicitly and frames follow-ups as questions.

---

## Future Improvements

- [ ] Build a small labeled dataset of real slop/non-slop PRs and calibrate the weights against it.
- [ ] Hallucinated-API check: verify that called functions/methods actually exist in the imported package version.
- [ ] Per-repo config file (`.slop-detector.yml`) for thresholds, disabled signals, and trusted authors.
- [ ] Run as an MCP server so other agents (and editors) can call it.

---

## License

*This project is contributed under the repository's open-source license.*
