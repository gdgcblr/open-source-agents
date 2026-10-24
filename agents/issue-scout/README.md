# Issue Scout

> Finds open-source issues you can actually work on: not claimed, not already fixed, no PR in flight, in repos that merge outside PRs. Then gives you a starter brief so your first PR takes hours, not days.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: New contributors lose evenings to issues that look open but aren't. Someone already claimed them in a comment, or a PR that fixes them is already open, or a contributor notes the feature "already exists on master", or the repo hasn't merged an outsider's PR in months. GitHub search can't see most of this. In two real runs on 24 Oct 2026, the issue search with `no:assignee -linked:pr` (GitHub's own "nobody is on this" filters) still returned issues that already had PRs: **6 of the 10** issues checked in the first run, **3 of 10** in the second. Those PRs reference the issue without being formally "linked", so only the issue timeline shows them.
- **Intended Users**: First-time and returning open-source contributors (hackathon and event attendees, students, developers looking for their next contribution), plus the AI coding assistants they use.

### Key Features
- **Dead-end filter with evidence**: reads each issue's timeline to detect open/merged PRs, assignments, "can I work on this?" claims, and "already fixed" or duplicate comments. Every warning links to the comment or PR that caused it.
- **Merge-likelihood check**: measures how often a repo merges PRs from outside contributors and how fast (median days), so you avoid repos where outside PRs go to die.
- **Fit to your time**: ranks by freshness, competition, clarity and a rough effort estimate against the hours you have. Penalises RFC/discussion issues that still need a maintainer decision.
- **Related work and duplicates**: finds similar open and closed issues and merged PRs in the same repo, so you learn from prior fixes and don't duplicate work.
- **Starter brief**: likely files to touch, house rules from the repo's CONTRIBUTING guide (CLA, DCO sign-off, Conventional Commits, changelog, test and lint commands) and, with Gemini, a summary, suggested approach, risks and questions to ask maintainers.
- **Three ways to use it**: a CLI, a conversational **Google ADK** agent (`adk web`) and an **MCP server** for Gemini CLI, Claude Code, Cursor and other MCP hosts.
- **Works with no keys**: everything except the Gemini brief and chat runs on GitHub's public API alone. The core needs only the Python standard library.

---

## Technical Stack

- **Language & Runtime**: Python 3.11+ (the deterministic core also runs on 3.9+ with the standard library only)
- **Agent Framework / Core Library**: Google Agent Development Kit (ADK) 2.13 (`LlmAgent` with function tools; a second `LlmAgent` with a Pydantic `output_schema` for briefs), Model Context Protocol Python SDK (`FastMCP`)
- **Models**: Gemini (default `gemini-3.5-flash`, configurable)
- **External APIs / Tools**: GitHub REST API (search, issue timeline, pulls, community profile, contents, git trees), read-only

---

## Architecture & Data Flow

```
 Profile (languages, topics, hours | GitHub username)
        |
        v
 [1] Repo search: active, >=100 stars, has good-first/help-wanted issues,
     sorted by how many help-wanted issues they carry          (1-4 search calls)
        |
        v
 [2] Issue search across those repos, 6 repos per query:
     open, unassigned, -linked:pr, beginner labels, updated within a year
        |
        v
 [3] Cheap pre-rank on search data -> top 10 (25 with GITHUB_TOKEN)
        |
        v
 [4] Evidence, in parallel:   issue timeline  -> claims, PRs, "already fixed", maintainer policy
                              recent closed PRs -> outside merge rate and median merge time
        |
        v
 [5] Deterministic scoring -> READY / CAUTION / SKIP + reasons + evidence links
        |
        +--> CLI (Markdown / JSON)
        +--> MCP server tools ------------> host model (Gemini CLI, Claude Code, Cursor...)
        +--> ADK root_agent (adk web/run) -> Gemini explains and plans, calling the same tools

 brief <issue>: inspect + related issues/PRs + CONTRIBUTING rules + likely files (git tree)
                --> ADK brief_writer (Gemini, structured StarterBrief) or facts-only without a key
```

Every verdict comes from deterministic code and links to its evidence. Gemini summarises and plans from those facts. It never decides whether an issue is available.

---

## Prerequisites

- Python 3.11+ (3.12 tested) for the full project; Python 3.9+ is enough for the CLI core
- pip
- Optional: a GitHub token (raises the API limit from 60 to 5,000 requests per hour)
- Optional: a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey), used for Gemini briefs and the ADK chat agent

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/issue-scout
   ```

2. **Set up the virtual environment / install dependencies:**
   ```bash
   python3.12 -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Configure Environment Variables (optional):**
   ```bash
   cp .env.example .env
   # then uncomment and fill in GITHUB_TOKEN and/or GOOGLE_API_KEY
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GITHUB_TOKEN` | No | *None* | Raises GitHub's limit to 5,000 requests per hour and lets each `find` check 25 issues instead of 10. A fine-grained token with no extra permissions is enough. |
| `GOOGLE_API_KEY` | Only for Gemini features | *None* | Gemini API key for `brief` summaries, `adk web` and `adk run`. `GEMINI_API_KEY` is also accepted. |
| `ISSUE_SCOUT_MODEL` | No | `gemini-3.5-flash` | Gemini model used by both ADK agents. |
| `ISSUE_SCOUT_FALLBACK_MODELS` | No | `gemini-3.8-flash,gemini-3.5-flash-lite` | Comma-separated models the `brief` command tries, in order, when the main model is overloaded or rate-limited (HTTP 429/5xx). |

The CLI and the ADK entry point both read `agents/issue-scout/.env`. Real environment variables take precedence.

---

## How to Run

### CLI

```bash
# Shortlist issues for you
python -m issue_scout find --lang python --hours 3
python -m issue_scout find --lang typescript,go --topic developer-tools --limit 8
python -m issue_scout find --user <your-github-username>        # infer languages from your repos
python -m issue_scout find --lang rust --max-stars 20000 --show-skipped

# Before you start an issue someone sent you
python -m issue_scout inspect https://github.com/owner/repo/issues/123
python -m issue_scout related owner/repo#123

# Plan the first PR (Gemini adds summary/approach/risks when GOOGLE_API_KEY is set)
python -m issue_scout brief owner/repo#123
python -m issue_scout brief owner/repo#123 --no-ai

# Any command: --json for machine-readable output
```

### Google ADK chat agent

```bash
adk web adk_agents             # open http://localhost:8000 and pick "issue_scout_agent"
adk run adk_agents/issue_scout_agent
```

Try: *"I know Python and have 3 hours tonight, find me something"*, then *"make me a plan for #2"*.

### MCP server (Gemini CLI, Claude Code, Cursor, ...)

The server needs no model key: your assistant does the reasoning, and Issue Scout supplies the GitHub evidence. Replace `/ABS/PATH` with the absolute path to this folder.

Gemini CLI (`~/.gemini/settings.json`) or Cursor (`.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "issue-scout": {
      "command": "/ABS/PATH/agents/issue-scout/.venv/bin/python",
      "args": ["-m", "issue_scout", "mcp"],
      "cwd": "/ABS/PATH/agents/issue-scout",
      "env": { "PYTHONPATH": "/ABS/PATH/agents/issue-scout" }
    }
  }
}
```

Claude Code:
```bash
claude mcp add issue-scout -e PYTHONPATH=/ABS/PATH/agents/issue-scout -- /ABS/PATH/agents/issue-scout/.venv/bin/python -m issue_scout mcp
```

Tools exposed: `find_issues`, `inspect_issue`, `related_issues`, `repo_conventions` and `starter_brief_facts`.

---

## Example Input & Output

All outputs below are from real runs on 24 Oct 2026, unauthenticated, trimmed only where marked. GitHub data changes constantly, so your results will differ.

### Example Input
```bash
python -m issue_scout find --lang python --hours 3 --limit 4
```

### Example Output
```
## Issue Scout: 4 picks for python, ~3h

1. **[READY 90]** [brekkylab/backlot#988](https://github.com/brekkylab/backlot/issues/988) confluence: a body's storage writes a character HTML 4 names as itself and ' as &#x27;, where real writes the named entity and ' as is
   - effort: medium (rough guess) | updated 1 days ago | 0 comments | labels: good first issue, help wanted, fidelity, hacktoberfest
   - repo: 298 stars, merges 92% of recent outside PRs, median 0.6 days to merge
   - why: active in the last two weeks; merges 92% of recent outside PRs; outside PRs merge in ~0.6 days; labelled for newcomers

2. **[CAUTION 84]** [repowise-dev/repowise#4575](https://github.com/repowise-dev/repowise/issues/4575) A named arrow function inside a function rolls up into it, and a function's NLOC counts the functions nested in it
   - effort: large (rough guess) | updated today | 2 comments | labels: bug, help wanted
   - repo: 7.9k stars, merges 92% of recent outside PRs, median 2.6 days to merge
   - ! probably more work than the time you have
   - why: active in the last two weeks; merges 92% of recent outside PRs; outside PRs merge in ~2.6 days; maintainers have commented

[... picks 3 and 4 trimmed ...]

**Filtered out 3 dead ends** that GitHub search still listed: 2 already had an open PR, 1 had a merged PR.

_Checked 20 repos with 20 GitHub API calls._
_Note: No GITHUB_TOKEN set: checked fewer issues to stay inside GitHub's anonymous rate limit._
```

### Catching an issue that only looks open
This `good first issue` has no assignee and no linked PR, so GitHub search lists it as available:
```bash
python -m issue_scout inspect https://github.com/Significant-Gravitas/AutoGPT/issues/9416
```
```
**[CAUTION 32]** [Significant-Gravitas/AutoGPT#9416](https://github.com/Significant-Gravitas/AutoGPT/issues/9416) Custom Replicate Model Block
   - effort: small (rough guess) | updated 2 days ago | 6 comments | labels: good first issue
   - repo: 187.7k stars, only 2 of the last 50 closed PRs came from outside contributors
   - ! a contributor says it may already be fixed; confirm first -> @albatrossflyon-coder: "This already exists on `master` — `ReplicateModelBlock` (`backend/blocks/replic..." https://github.com/Significant-Gravitas/AutoGPT/issues/9416#issuecomment-4931514943
   - ! an earlier PR was closed without merging -> #10324 https://github.com/Significant-Gravitas/AutoGPT/pull/10324
   - why: active in the last two weeks; labelled for newcomers
```

### Starter brief (facts only, no Gemini key)
```bash
python -m issue_scout brief brekkylab/backlot#988
```
```
## Starter brief: [brekkylab/backlot#988](https://github.com/brekkylab/backlot/issues/988) confluence: a body's storage writes a character HTML 4 names as itself and ' as &#x27;, where real writes the named entity and ' as is

**Verdict:** READY (score 90) | effort: medium (rough guess)

### Where to look
- `backlot/graphql/body.py` - matches: body
- `backlot/schemas/confluence.schema.json` - matches: confluence, json
- `backlot/fidelity/baseline/confluence.json` - matches: confluence, json
- `examples/using-official-sdk/confluence.py` - matches: confluence
- `backlot/data/confluence_search_options.wadl` - matches: confluence
- `examples/using-llamaindex-readers/confluence.py` - matches: confluence

### Prior work
#### Open related issues
- [#983](https://github.com/brekkylab/backlot/issues/983) confluence: a character past U+FFFF in a title, a body or a comment is written as its UTF-8 bytes, where real writes two \u escapes
- [#984](https://github.com/brekkylab/backlot/issues/984) confluence: content/{id} sent no expand expands body.storage, where real expands space, history and version, and a sent expand gets space added

#### Closed related issues
- none found

#### Merged PRs on the same topic
- none found

### House rules
From [the contributing guide](https://github.com/brekkylab/backlot/blob/main/CONTRIBUTING.md):
- Setup: `uv venv && source .venv/bin/activate` | `uv pip install -e ".[dev]"` | `python scripts/prose_check.py` | `uv sync --all-extras --locked`
- Test: `pytest` | `pytest -rs`
- Lint: `ruff check . && ruff format --check .` | `ruff check --preview --select PLW1514 .`

_Note: Gemini brief skipped: set GOOGLE_API_KEY to add a summary and plan._
```

### Starter brief with Gemini
With `GOOGLE_API_KEY` set, the same command runs the ADK `brief_writer` agent. Its output is validated against the `StarterBrief` schema, and these sections are added above the facts (excerpt, same issue):
```
### Summary (gemini-3.5-flash)
Backlot's Confluence emulator uses standard HTML escaping on body representations, escaping single quotes as &#x27; and leaving named entity characters as unescaped literals. Real Confluence Cloud leaves single quotes unescaped across view and storage formats and encodes HTML4 named characters (except U+0160 and U+0161) as entity references in storage mode.

### Suggested approach (Gemini, verify before coding)
1. Locate where Confluence body representations (_storage, _view, _export_view) are constructed in the Confluence mock handlers.
2. Replace standard html.escape with a custom helper function for Confluence body representations.
3. For storage bodies, map non-ASCII characters present in Python's html.entities.codepoint2name to their named entities (excluding U+0160 and U+0161), and leave single quotes (') unescaped.
4. For view and export_view bodies, ensure only &, <, >, and " are escaped while keeping single quotes (') as literal characters.
5. Add reproduction unit tests over the HTTP endpoint verifying storage, view, and export_view output against expected entity encodings.
6. Run pytest and ruff check . to verify tests pass and code style guidelines are met.

### Questions worth asking first
- Should the custom HTML4 entity escaping logic for Confluence be isolated to a helper within the Confluence provider or added as a general utility in Backlot?

### Risks
- Care must be taken to only convert raw text characters to HTML4 entity references without double-escaping existing markup tags or standard HTML entities like &quot;.
```

### Chatting with the ADK agent
A real two-turn session with `root_agent` (the agent behind `adk web adk_agents`). Gemini picks the tools itself. Tool calls are shown in brackets, and the replies are trimmed:
```
>>> USER: I know Python and have about 3 hours tonight. Find me 3 issues I can actually work on.
[tool call] find_issues({'languages': ['python'], 'hours': 3, 'limit': 3})
<<< AGENT:
Here are 3 open Python issues matched to your 3-hour window.
*(Filtered out **4 dead ends**: 2 already had open PRs and 2 had merged PRs.)*

### 1. [brekkylab/backlot#988](https://github.com/brekkylab/backlot/issues/988)
* **Verdict:** Ready
* **Score:** 90/100
* **Estimated Effort:** Medium *(heuristic)*
* **Why it's a good pick:** High outside PR merge rate (92% merged, ~0.6 days turnaround), labelled for newcomers, detailed description, and no competing claims or PRs.
[... picks 2 and 3 trimmed ...]

>>> USER: Make me a plan for the first one.
[tool call] starter_brief_facts({'hours': 3, 'issue': 'brekkylab/backlot#988'})
<<< AGENT:
### 3. Prior Work to Review
* Check issue **#983** (*"confluence: a character past U+FFFF in a title..."*), as #988 was discovered while measuring behavior for it.

### 4. House Rules & Setup Commands
* **Running Tests:** pytest   # or for detailed summary: pytest -rs
* **Linting & Code Style:** ruff check . && ruff format --check .
[... goal, files, setup and questions trimmed ...]
```

---

## How to Test

```bash
pytest
```

- 71 offline tests: no network, no API keys. GitHub is replaced by a fake client.
- Covered: claim, "already fixed" and maintainer-policy detection; timeline and PR parsing; repo merge statistics; scoring and verdicts; related-issue search; CONTRIBUTING parsing; likely-file ranking; the full `find` pipeline including rate-limit fallbacks; the GitHub client (search pacing, secondary-rate-limit retries, error messages); the CLI; and the tool layer.
- `tests/test_adk_agent.py` drives the **real ADK runner** with a scripted model. It checks three things:
  - `root_agent` calls Issue Scout's tools and receives their results.
  - Gemini briefs are validated against `StarterBrief`.
  - The untrusted-content instruction reaches the model.
  It is skipped automatically if `google-adk` isn't installed.
- **Manual check:** `python -m issue_scout inspect https://github.com/Significant-Gravitas/AutoGPT/issues/9416` should flag the "already exists" comment and the closed PR #10324. These are public, so results can change if the thread changes.

---

## Known Limitations

- **Heuristics, not certainty**: claim and "already fixed" detection uses English phrase patterns. It misses some wordings and occasionally misreads a comment, which is why each flag links to the comment so you can judge. Effort estimates are rough guesses from labels and description length.
- **Rate limits**: without `GITHUB_TOKEN`, GitHub allows 60 requests per hour. One `find` uses about 20 and one `brief` about 10. The tool checks fewer issues when unauthenticated and returns partial results with a note if the limit is hit. Search is limited to 10 queries per minute unauthenticated (30 with a token).
- **GitHub's secondary rate limit**: many searches in a short burst (for example several `find` and `brief` runs back to back) can trigger GitHub's abuse protection, even with a token. Issue Scout spaces searches at least 1 s apart and retries twice, after 5 s and 15 s (or after `Retry-After`). If the limit persists, it says so plainly; wait a few minutes.
- **Gemini availability**: popular models sometimes return 503 "high demand". `brief` falls back through `ISSUE_SCOUT_FALLBACK_MODELS` and, if every model fails, still prints the facts-only brief. The `adk web` chat uses the main model only.
- **Sampling**: merge statistics use the 50 most recently updated closed PRs, and fewer than 3 outside PRs is treated as "not enough data". Bots and core-team PRs are excluded by GitHub's `author_association`.
- **GitHub only**: GitLab, Codeberg and other forges are not supported.
- **Large repos**: likely-file suggestions use the git tree API, which GitHub truncates for very large repositories, so suggestions may be incomplete there.
- **Gemini sections** depend on the model and can be wrong. The brief labels them as suggestions to verify.
- **Testing**: tested on macOS (Python 3.12 for everything, 3.9 for the core). Linux should work; Windows is untested.

---

## Security & Privacy Considerations

- **Secrets Handling**: keys are read from environment variables or a local `.env` (git-ignored; only `.env.example` with placeholders is committed). The GitHub token is sent only to `api.github.com`, and only read endpoints are called.
- **Data Privacy**: only public GitHub data is fetched. With a Gemini key, the facts for one issue (public issue text, related titles, CONTRIBUTING excerpts and file paths) are sent to the Gemini API. Nothing is stored on disk. Responses are cached in memory for the life of the process.
- **Safety**: the tool never writes to GitHub (no comments, no claims, no PRs) and never executes code from repositories. Issue text is untrusted input: both ADK agents and the MCP server instructions tell the model to treat it as data and never follow instructions inside it. Availability verdicts are computed in code, never by the model.

---

## Future Improvements

- [ ] Optional on-disk cache with ETags to save rate limit across runs
- [ ] Watch mode: notify when a matching new issue appears
- [ ] Detect claims in more languages and via linked branches
- [ ] Learn from your merged PRs to personalise ranking
- [ ] GitLab support

---

## License

*This project is contributed under the repository's open-source license.*
