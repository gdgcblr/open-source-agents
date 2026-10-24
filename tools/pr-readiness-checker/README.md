# pr-readiness-checker

> Tells you whether your open-source-ai contribution will pass review, before a maintainer has to.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Contributions to this repository get sent back for the same avoidable reasons: a folder
  name that isn't kebab-case, README sections left as template text, no dependency manifest, an API key
  committed by accident, or edits outside the project folder. Each round trip costs the contributor and
  the maintainers time, and a leaked key can't be taken back once it is pushed.
- **Intended Users**: Anyone contributing to `agents/` or `tools/` (especially during a buildathon), and
  maintainers who want a quick first-pass review.

### Key Features
- **17 rule checks** taken straight from `CONTRIBUTING.md` and the PR template, each with an ID
  (S1-S4, D1-D4, M1-M2, X1-X4, G1-G3) and a fix suggestion.
- **Secret scanning** for Google, OpenAI, Anthropic, GitHub, AWS, Slack and Hugging Face keys plus
  private key blocks, with masked output so the report itself never leaks the key.
- **PR scope check** against `upstream/main`: flags files changed outside your folder and root-level
  dependency files.
- **Optional Gemini README review** (`--ai`): scores clarity, setup, examples, limitations and security
  disclosure, with concrete fixes. Advisory only; it never changes the pass/fail result.
- **CI-friendly**: exit codes, `--json` output with a versioned schema, `--strict` mode.
- **Evals included** for the rules, the secret scanner and the AI review (see [evals/README.md](evals/README.md)).

---

## Technical Stack
- **Language & Runtime**: Python 3.11+ (developed on 3.12)
- **Core Library**: plain Python; [Typer](https://typer.tiangolo.com/) for the CLI, Rich for output,
  Pydantic for the report schema
- **Models**: Gemini via the `google-genai` SDK, default `gemini-3.6-flash` (optional)
- **External Tools**: the `git` CLI (read-only) for file listing and scope checks

---

## Architecture & Data Flow

```
prcheck check <folder>
      |
      v
 build_context()  -- lists the files git would commit, finds the repo root,
      |              loads template/README.md and the base branch diff
      v
 registry of checks (prcheck/checks/*.py) -- each reads the context, returns findings
      |
      v
 Report (pydantic, schema_version "1") --> terminal view / --json / exit code
      |
      +--> --ai: secret gate -> redact -> Gemini (structured JSON) -> validate -> advisory scores
```

Design choices that keep it easy to extend:
- **Rules live in data** ([prcheck/data/rules.toml](prcheck/data/rules.toml)), not in code, so a per-repo
  rules file can be added later without touching checks.
- **New check = one decorated function.** The runner, CLI, JSON report and `prcheck rules` pick it up.
- **Checks only read a shared `ProjectContext`**, so new inputs (a sandboxed install run, a PR diff from
  the GitHub API) can be added in one place.
- **The model sits behind a `ReviewProvider` interface**, so Gemini can be swapped for another model or a
  test double, and the planned fix-mode agent can reuse it.
- **One entry point (`runner.run`) and a versioned JSON report** are what an MCP server or GitHub Action
  will build on. See [ROADMAP.md](ROADMAP.md).

---

## Prerequisites
- Python 3.11 or newer
- `git` on your PATH (without it, scope checks are skipped and files are listed from disk)
- For `--ai` only: a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

---

## Installation & Setup

```bash
cd tools/pr-readiness-checker
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -e .            # core checks only
pip install -e ".[ai,dev]"  # plus Gemini review and the test tools
```

For `--ai`, create a `.env` from the example and add your key:

```bash
cp .env.example .env
```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Only for `--ai` | *None* | Gemini key (`GOOGLE_API_KEY` also works) |
| `MODEL_NAME` | No | `gemini-3.6-flash` | Gemini model id; `--model` overrides it |

The core checks need no configuration. Rule values (generic names, required sections, secret file
patterns, base branches) are in `prcheck/data/rules.toml`.

---

## How to Run

Run from the repository root (or anywhere, with a path to the project folder):

```bash
prcheck check tools/my-project              # all checks, compared with upstream/main
prcheck check tools/my-project --ai         # plus Gemini README feedback
prcheck check tools/my-project --json       # machine-readable report
prcheck check tools/my-project --strict     # warnings also block
prcheck check tools/my-project --base origin/main
prcheck check tools/my-project --no-git     # skip git; list files from disk
prcheck rules                               # every check and the rule it comes from
```

| Exit code | Meaning |
| :--- | :--- |
| `0` | Ready: no errors (and no warnings with `--strict`) |
| `1` | Not ready |
| `2` | Usage error, e.g. the folder does not exist |
| `3` | A check crashed: a bug in prcheck, never reported as a pass |

---

## Example Input & Output

### Example Input
A sample project generated by the eval fixtures: folder `tools/My_Agent`, the untouched template README,
no `requirements.txt`, a committed `.env`, and a (fake) Gemini key hard-coded in `config.py`.

```bash
prcheck check tools/My_Agent --no-git
```

### Example Output
Captured from a real run on 2026-10-24 (long lines and repeated SKIP lines trimmed):

```
pr-readiness-checker 0.1.0 | tools/My_Agent
files: filesystem | template: repo | base: none

FAIL S2 Folder name is lowercase kebab-case
       - 'My_Agent' is not lowercase kebab-case; try 'my-agent'.
FAIL S3 Folder name is descriptive, not generic
       - 'My_Agent' is too generic; pick a name that says what the project does.
FAIL M1 Dependencies are declared in a manifest
       - No dependency manifest found (requirements.txt, pyproject.toml, package.json, go.mod, ...).
FAIL X1 No secret or credential files
       - '.env' must not be committed; delete it or add it to .gitignore. (.env)
FAIL X2 No API keys or tokens in file contents
       - Google API key found (AIza...LOz). Revoke it and load it from an environment variable. (config.py:1)
WARN D3 No leftover template text
       - 39 line(s) still contain template text: line 1: "# [Project Name]"; ... (README.md:1)
SKIP M2 Dependency versions are pinned
       No manifest to inspect (see M1).
SKIP G1 Changes stay inside the project folder
       Git checks disabled (--no-git).
...
PASS 7 check(s): S1, S4, D1, D2, D4, X3, X4

Result: NOT READY | 5 error(s), 1 warning(s), 0 note(s) | 40 ms
```

With `--ai` the report adds an advisory block, scored 1-5 per criterion with a short reason each, the top
fixes, token counts and latency. If X1/X2 find anything, the AI step is skipped and nothing is sent.

---

## How to Test

```bash
pytest                                   # 32 tests, offline, about 20 s
python -m evals.run_checks_eval          # 56 labelled cases, precision/recall per check
python -m evals.run_secrets_eval         # generated keys vs look-alike decoys
python -m evals.run_ai_eval --provider static   # AI eval harness, offline
python -m evals.run_ai_eval              # live Gemini eval (needs GEMINI_API_KEY)
```

Latest results (2026-10-24):

| Suite | Result |
| :--- | :--- |
| Unit tests | 32 passed |
| Rule-check eval | 56/56 cases correct (15 of them reproduce false alarms seen on real PRs); precision and recall 1.00 for all 17 checks |
| Secret-scanner eval | 100% recall for every key type (300 per type, 4 seeds); 0 false positives on 3,900 decoy lines per seed, including fake test tokens and documentation example keys |
| Real PRs on gdgcblr/open-source-agents | All 56 project folders in 53 open PRs, no crashes, 0.3-1 s each; details below |
| AI review eval (live) | Not complete: a single pass over 3 of the 4 READMEs agreed with the seed labels (MAE 0.20) and resisted the injection README; the 4th hit a temporary 503 (retries were added), and the 3-run consistency test was stopped by the free-tier quota (HTTP 429) |
| `--ai` on this README (live) | Worked: `gemini-3.6-flash`, 3,246 input / 367 output tokens, about 10 s, 1 attempt. It scored 5/5 on every criterion, which may mean the model is lenient; the human-labelled eval is what will show that |

Building this surfaced two real bugs, both now covered by eval cases: the secret eval caught Google keys
ending in `-` or `_` being missed, and running prcheck on its own folder caught D3 flagging template
text quoted inside a code block.

### Validation on real pull requests (2026-10-24)
prcheck was run, read-only, on every open PR in the upstream repository, and each verdict was checked by
hand. The first pass exposed false alarms that each became an eval case before being fixed:
template scaffolding lines reported as leftovers (16 of 20 folders), headings such as "Quick Start",
"Safety Guardrails", "Roadmap" or "CLI" not recognised, AWS's published example key, obviously fake test
tokens and private-key headers without key material reported as leaked secrets, and `<project-slug>` in
prose. It also missed committed `.adk/` session folders, which is now X4.

After the fixes, 37 of 56 folders are ready. The ones that are not have real problems found by hand
review: a project outside `agents/`/`tools/` (S1), two projects in one PR (G1, 3 PRs), capitals or
underscores in folder names (S2), no dependency manifest (M1), missing required README sections (D2), an
empty example section (D4) and committed ADK session data (X4, 3 PRs). No missed secrets, credential
files, virtual environments or caches were found in a separate scan of every PR.

---

## Known Limitations
- **Rules are specific to this repository.** They come from its CONTRIBUTING.md; other repos need their
  own `rules.toml` (planned).
- **It can't tell whether your code runs.** It checks that setup is documented, not that it works on a
  clean machine (sandboxed install run is on the roadmap).
- **The secret scanner is pattern-based.** It knows the providers listed above plus a generic
  `name = value` heuristic; keys from other providers in unusual formats can be missed. It is a safety
  net, not a replacement for GitHub secret scanning. Values that are clearly not real (AWS documentation
  examples, sequential runs such as `abcdef`/`123456`, words like `fake` or `dummy`, private-key headers
  with no key body) are reported as notes instead of errors; a reviewer should still glance at them.
- **README section matching uses keywords** (e.g. a heading containing "usage" counts as "How to Run"),
  so creative headings may be reported as missing.
- **AI scores are opinions.** The labels in `evals/readme_golden/labels.toml` are seed labels written
  while building the tool, not independent human judgements, and the live eval is not complete yet.
- **Free-tier Gemini limits** can return 429 after a burst of calls; prcheck reports it and moves on.
- Tested on Windows 11 with Python 3.12 and git 2.55. Linux and macOS are untested.

---

## Security & Privacy Considerations

- **Secrets Handling**: The Gemini key is read from the environment or a local `.env` (git-ignored) and is
  never printed or logged. Any secret prcheck finds is masked in its output (`AIza...LOz`).
- **Data Privacy**: Without `--ai` nothing leaves your machine. With `--ai`, only README text is sent to
  Google's Gemini API, never code, and only after these guardrails:
  1. if X1 or X2 report anything, no call is made;
  2. the README is truncated to 20,000 characters;
  3. anything that still looks like a secret is replaced with `[REDACTED]`.
- **Safety**: prcheck never executes contributor code and only runs read-only git commands. The README is
  treated as untrusted input: it is fenced as data in the prompt, phrases like "ignore previous
  instructions" are flagged, model output must match a strict schema (one retry, then rejected), and the
  AI result can never change pass/fail.

---

## Future Improvements
Planned in sprints; details and design notes are in [ROADMAP.md](ROADMAP.md).
- [ ] Sprint 2: MCP server and `prcheck pr-body` (draft PR description from the PR template)
- [ ] Sprint 3: fix mode, an agent that repairs failing checks with your approval (Google ADK)
- [ ] Sprint 4: per-repo rules files, a GitHub Action that comments on PRs, sandboxed install runs
- [ ] Replace seed labels with human scores and finish the live AI eval

---

## License
Contributed under the repository's MIT license.
