# Contrib Sentinel

> A meta-agent that audits a submission to this repo against the standards in `CONTRIBUTING.md`, combining cheap static checks with a Claude review that adds judgment the static checks can't.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: `CONTRIBUTING.md` sets out four review criteria (reproducibility, documentation quality, security/privacy, focused scope), but checking a submission against them by hand is repetitive and easy to skip steps on. This agent automates the first pass.
- **Intended Users**: Maintainers reviewing an incoming PR to `agents/` or `tools/`, and contributors who want to self-check their own submission before opening one.

### Key Features
- Static checks with no API key required: directory naming convention, dependency manifest presence, `.gitignore` presence, a curated secret scan (by filename and by content pattern) over the project's tracked files, and README section coverage against `template/README.md`.
- Optional scope-isolation check (`--base <ref>`) that flags any changed file outside the target project directory.
- An optional Claude review pass that reads the static findings plus the full README and renders judgment the static checks can't make: whether examples look genuine or fabricated, whether limitations are honestly disclosed, and an overall PASS / NEEDS WORK / FAIL verdict.
- Works on a submission before it's even `git add`-ed: falls back to a plain filesystem walk when `git ls-files` finds nothing tracked yet.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: Vanilla script using the Anthropic Python SDK directly (no agent framework)
- **Models**: Claude (default `claude-sonnet-4-5-20250929`, configurable), used only for the optional review pass
- **External APIs / Tools**: Anthropic Messages API, local `git` CLI

---

## Architecture & Data Flow

```
[target directory] --> [static checks: naming, manifest, .gitignore, secrets, README sections, scope]
                                          |
                                          +--> [findings list]
                                          |
                     [findings + README text] --> [Claude review] --> [verdict + ranked issues]
```

Static checks always run and never leave the local machine. The Claude review step is purely
additive: if `ANTHROPIC_API_KEY` is unset or `--no-llm` is passed, the tool still prints the
full static-check report.

---

## Prerequisites

- Python 3.10+
- `pip`
- `git` available on your `PATH`, run from inside a git repository
- An Anthropic API key, only if you want the Claude review pass (https://console.anthropic.com/)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/contrib-sentinel
   ```

2. **Set up the virtual environment / install dependencies:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Configure environment variables (optional, enables the Claude review pass):**
   ```bash
   cp .env.example .env
   # then edit .env and set ANTHROPIC_API_KEY
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `ANTHROPIC_API_KEY` | No | *None* | Enables the Claude review pass. Without it, only static checks run. |
| `MODEL_NAME` | No | `claude-sonnet-4-5-20250929` | Claude model identifier to use for the review pass |

---

## How to Run

```bash
# Full audit (static checks + Claude review) of a submission
python main.py agents/some-contributor-agent

# Static checks only, no API key needed
python main.py tools/some-contributor-tool --no-llm

# Also flag files changed outside the project directory, relative to origin/main
python main.py agents/some-contributor-agent --base origin/main
```

---

## Example Input & Output

### Example Input
```
$ python main.py agents/diff-review-agent --no-llm
```

### Example Output
```
## Static checks for agents\diff-review-agent

- No static issues found.
```

Running this tool against its own directory during development caught two real issues before
they shipped: a false-positive secret match on `.env.example` (the filename regex needed to
exclude it explicitly, matching the `!.env.example` line in the shared `.gitignore` template),
and a genuinely missing `README.md` for this very project.

---

## How to Test

There is no automated test suite. To verify it manually:
1. Run `python main.py <any existing project dir> --no-llm` and confirm it prints a clean
   report with no false positives (naming, manifest, `.gitignore`, secrets, README sections).
2. Temporarily add a file containing the literal string `sk-ant-` followed by 20+ random
   alphanumeric characters to a test directory and confirm the secret-content check flags it;
   remove it afterward.
3. Run against a directory missing a `README.md` and confirm it's reported as missing entirely.
4. With `ANTHROPIC_API_KEY` set, run without `--no-llm` and confirm a verdict line (PASS /
   NEEDS WORK / FAIL) is printed under "## Claude review".

---

## Known Limitations

- The secret scanner is a small curated pattern list (AWS keys, OpenAI/Anthropic-style keys,
  PEM private key headers, hardcoded password assignments). It is not a substitute for a
  dedicated secret-scanning tool and will miss novel key formats.
- Deliberately does not execute the audited project's own code or install its dependencies —
  running arbitrary, unreviewed third-party contribution code automatically would itself be a
  security risk. Reproducibility is judged from the README's stated steps, not by executing them.
- The `--base` scope check is a simple path-containment comparison; it does not understand
  renames or distinguish an intentional, pre-approved multi-file change from scope creep.
- README section coverage is a heading-text match against `template/README.md`'s section names;
  a contributor who renames a section slightly may get a spurious "missing section" finding.
- The Claude review pass consumes API tokens per run and requires a paid/metered key.

---

## Security & Privacy Considerations

- **Secrets Handling**: `ANTHROPIC_API_KEY` is read from the environment (via `.env`, which is
  git-ignored) and is never logged or printed.
- **Data Privacy**: Only the target project's README content and the list of static findings
  are sent to the Anthropic API during the review pass; no other repository files are
  transmitted, and nothing is sent at all when `--no-llm` is used or no API key is set.
- **Safety**: This tool only reads files and runs read-only `git` commands (`rev-parse`,
  `ls-files`, `diff --name-only`). It never executes, installs, or imports code from the
  directory it audits.

---

## Future Improvements

- [ ] Optional sandboxed execution of the audited project's declared install step, behind an
      explicit opt-in flag, to actually verify reproducibility rather than inferring it from text.
- [ ] Emit a machine-readable (JSON) report mode for CI integration.
- [ ] Expand the secret pattern list and allow a repo-level custom pattern file.

---

## License

This project is contributed under the repository's open-source license (MIT).
