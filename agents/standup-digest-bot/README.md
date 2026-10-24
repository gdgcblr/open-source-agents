# Standup Digest Bot

> A local-first agent that turns your real GitHub activity into a daily standup update, grounds every claim in a verifiable event, and escalates to a human instead of inventing progress.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Writing a daily standup is repetitive and error-prone. People forget what they did, and when they rush it they write vague or slightly-wrong updates ("finished the refactor" when it was only started). An LLM asked to "summarize my day" will happily *hallucinate* plausible progress. The real challenge is not generating text, it is generating an update you can trust enough to post.
- **Intended Users**: Software engineers and teams who run async or synchronous daily standups and want a fast, honest first draft from their GitHub activity.

### Key Features
- **Grounded-by-construction digest**: The agent may only describe work that appears in the fetched activity log, and every "yesterday" bullet must cite the exact `[event_id]` it came from.
- **Anti-hallucination guardrail (`[confirm: ...]`)**: Any claim that cannot be matched to a real commit/PR/issue/review is *not* silently dropped or trusted. It is rewritten into a `[confirm: ...]` placeholder so a human verifies it. This is enforced in code, not just requested in the prompt.
- **Escalation / "when not to act"**: The agent refuses to produce a confident update when it shouldn't — an empty day, a partial fetch (a data source failed), or when too many claims needed confirmation. It returns a best-effort draft but flags `escalate=True` with reasons and a non-zero exit code so it is never auto-posted blindly.
- **Local-first, pluggable models**: Runs fully offline with a deterministic mock provider, locally via **Ollama** (default, no API key), or against **Gemini**/**OpenAI** if you opt in.
- **Built-in eval harness**: Scores groundedness (precision), coverage (recall), F1, and fabrication count against a ground-truth activity log, and checks escalation behavior per case.

---

## Technical Stack

- **Language & Runtime**: Python 3.9+
- **Agent Framework / Core Library**: Vanilla Python (framework-agnostic). A small typed pipeline: tool → prompt → LLM → verify/guardrail → digest.
- **Models**: Ollama local models (default, e.g. `llama3.1`) / Gemini (`gemini-2.5-flash`) / OpenAI (`gpt-4o-mini`) / deterministic `mock` for offline runs.
- **External APIs / Tools**: GitHub REST API (`/users/{user}/events`) as the agent's external capability.

---

## Architecture & Data Flow

```
                   +---------------------------+
   GitHub REST --> |  GitHubTool.fetch_day()   |  (external capability)
   or JSON file    +---------------------------+
                                |
                                v
                         ActivityLog  (typed, event_id-tagged facts)
                                |
                                v
   +-------------------------------------------------------------+
   |  StandupAgent.generate()                                    |
   |   1. Pre-flight escalation (empty? partial fetch?)          |
   |   2. Build evidence prompt (only real events)               |
   |   3. LLM drafts JSON digest, citing [event_id] per bullet   |
   |   4. GUARDRAIL: verify each cited id against the log;        |
   |      unsupported claims -> [confirm: ...] + escalate check  |
   +-------------------------------------------------------------+
                                |
                                v
                    Digest (text + escalate + needs_confirmation
                            + referenced_event_ids)
                                |
                 +-------------------------------+
                 |  Eval harness: precision /    |
                 |  recall / F1 / fabrication    |
                 +-------------------------------+
```

The key idea: the LLM never sees anything except real events, and anything it emits is checked back against those events before it reaches the user.

---

## Prerequisites

- Python 3.9+
- `pip`
- Optional: a running [Ollama](https://ollama.com) server for local generation (`ollama pull llama3.1`)
- Optional: a GitHub Personal Access Token (for private repos / higher rate limits)
- Optional: a Gemini or OpenAI API key if you choose those providers

No API keys or network access are required to run the offline demo or the evals.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/standup-digest-bot
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

3. **Configure Environment Variables (optional for the offline demo):**
   ```bash
   cp .env.example .env    # Windows: Copy-Item .env.example .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `LLM_PROVIDER` | No | `ollama` | `ollama` \| `gemini` \| `openai` \| `mock` |
| `LLM_MODEL` | No | provider default | Model id (e.g. `llama3.1`, `gemini-2.5-flash`, `gpt-4o-mini`) |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Local Ollama server URL |
| `GEMINI_API_KEY` | Only for Gemini | *None* | Key when `LLM_PROVIDER=gemini` |
| `OPENAI_API_KEY` | Only for OpenAI | *None* | Key when `LLM_PROVIDER=openai` |
| `GITHUB_TOKEN` | No* | *None* | PAT for private repos / higher rate limits (*recommended for real runs) |
| `GITHUB_USERNAME` | No | *None* | Default user to summarize if `--user` is omitted |
| `LOG_LEVEL` | No | `info` | `debug` \| `info` \| `warn` \| `error` |

Never commit a real `.env`. Only `.env.example` (with placeholders) is tracked.

---

## How to Run

```bash
# 1) Fully offline demo - no keys, no network (deterministic mock LLM + sample data):
python main.py --test-mode

# 2) Real run against GitHub using a local Ollama model:
python main.py --user octocat --date 2026-10-24

# 3) Use a hosted provider:
python main.py --user octocat --provider gemini --model gemini-2.5-flash

# 4) Summarize a saved activity file instead of calling GitHub:
python main.py --from-file sample_activity.json --provider mock

# 5) Emit the full structured Digest as JSON:
python main.py --test-mode --json
```

Exit codes: `0` = grounded draft ready, `3` = draft produced but flagged for human review (escalation), `2` = usage error.

### Demo web UI

A dependency-free, single-page web UI (stdlib `http.server` only) for live demos. It reuses the exact same agent pipeline as the CLI, so what you see in the browser is the real thing.

```bash
python webapp/server.py            # then open http://localhost:8000
python webapp/server.py --port 9000
```

In the UI you can:
- Pick a bundled **real-data fixture** (torvalds, gaearon, sindresorhus, ...) or fetch **live GitHub** by username + date.
- Choose the LLM provider/model (`mock` for an instant offline demo, `ollama` for local).
- See the digest with **grounded bullets** (each tagged with its real `[event_id]`) visually separated from **`[confirm]`** placeholders, an escalation banner when the agent declines to vouch for the draft, live metrics (events fetched / grounded refs / needs-confirm), and an expandable **evidence panel** showing the exact real events the agent was allowed to use.

Tip: start with the `mock` provider for a snappy, reproducible demo, then switch to `ollama` to show a real model producing the same grounded structure.

### Running against real GitHub accounts

The repo ships scripts and genuine captured data so you can run the agent on real activity, not just the synthetic sample:

```bash
# Live demo across real public maintainers (torvalds, gaearon, sindresorhus):
python scripts/demo.py                    # live GitHub fetch + deterministic mock LLM
python scripts/demo.py --provider ollama  # live GitHub + your local model
python scripts/demo.py --user <you> --date 2026-10-04   # a single live run

# Snapshot any real user's day into a replayable JSON fixture:
python scripts/capture_activity.py --user torvalds --date 2026-10-04 \
    --out evals/fixtures/torvalds_2026-10-04.json

# Replay a captured real day offline (no network, no rate limits):
python main.py --from-file evals/fixtures/torvalds_2026-10-04.json --provider mock
```

Set `GITHUB_TOKEN` to avoid GitHub's low anonymous rate limit. The public Events
API exposes roughly the last 90 days, so very old pinned dates will return no
events (and the agent then correctly escalates).

**Bundled real-data fixtures** (captured from live GitHub, checked in so reviewers can reproduce without a token):
- `evals/fixtures/torvalds_2026-10-04.json` — 11 events across `linux` and a side project (commits, a merged PR, a PR comment)
- `evals/fixtures/gaearon_2026-10-21.json` — a high-volume day (100+ events, exercises pagination)
- `evals/fixtures/sindresorhus_2026-10-23.json` — a busy multi-repo day

---

## Example Input & Output

### Example Input (real captured GitHub data)
A genuine day of `torvalds` activity captured from the live GitHub API into `evals/fixtures/torvalds_2026-10-04.json` (11 events across the `linux` and `GuitarPedal` repos), run with:
```bash
python main.py --from-file evals/fixtures/torvalds_2026-10-04.json --provider mock
```

### Example Output (actual run)
```
=== Standup for torvalds - 2026-10-04 ===

**Yesterday:**
- [push:torvalds/GuitarPedal@44b48bf] commit in torvalds/GuitarPedal: Pushed 1 commit to main
- [pr:torvalds/GuitarPedal#48] pull_request in torvalds/GuitarPedal (merged): PR #48
- [comment:torvalds/GuitarPedal#48] review in torvalds/GuitarPedal (created): Commented on PR #48: Fade the global bypass the right way round
- [push:torvalds/linux@6addb4f] commit in torvalds/linux: Pushed 1 commit to master
- [push:torvalds/linux@06ac073] commit in torvalds/linux: Pushed 1 commit to master
  ... (11 events total)

**Today:**
- [confirm: add today's plan]

**Blockers:**
- (none)

Looks grounded. Safe to post after a quick glance.
```

The synthetic `sample_activity.json` (a commit, merged PR, opened issue, and PR review) is also available for a quick `python main.py --test-mode` run.

On an **empty day**, the agent does not invent anything — it returns an escalation:
```
[ESCALATION] This draft should be reviewed by a human before posting:
  - No tracked GitHub activity was found for this day, ...
```

---

## How to Test

```bash
# Run the eval harness (offline, deterministic mock provider):
python evals/run_evals.py

# Score a real model instead:
python evals/run_evals.py --provider ollama
```

The harness reports precision / recall / F1 / fabricated-claim count per case and verifies escalation behavior. The suite covers a synthetic normal day, an empty day (must escalate), a partial fetch (must escalate), **and three real captured GitHub days** (torvalds, gaearon, sindresorhus). A clean run prints `RESULT: 6/6 cases passed`.

---

## Known Limitations

- Uses the GitHub public **Events API**, which reflects recent activity (roughly the last ~90 events / 90 days) and can lag by a short delay. Very old days or very high-volume days may be truncated.
- Private-org activity requires a `GITHUB_TOKEN` with appropriate scopes; without it only public activity is visible.
- Event attribution is per authenticated/looked-up user; co-authored commits are attributed by the push actor.
- The `mock` provider is intentionally simple (one grounded bullet per event); it is for reproducible offline demos and evals, not polished prose.
- Quality of the prose (not the grounding) depends on the chosen model. Grounding and escalation guarantees are enforced in code regardless of model.
- Tested on Windows and Linux with the offline/mock path. Live GitHub + Ollama paths require the respective services running locally.

---

## Security & Privacy Considerations

- **Secrets Handling**: All credentials are read from environment variables (via `.env`, which is git-ignored). Only `.env.example` with placeholders is committed. No keys are logged.
- **Data Privacy**: With the `mock` or `ollama` provider, no activity data leaves your machine. With `gemini`/`openai`, the evidence lines (commit messages, PR/issue titles) are sent to that provider — use a local provider if your titles are sensitive.
- **Safety**: The agent executes no shell commands and performs no writes. It only reads GitHub activity and generates text. It never auto-posts: an escalated draft returns a non-zero exit code so an automation step can require human review.

---

## Future Improvements

- [ ] Cache GitHub responses to reduce rate-limit pressure.
- [ ] Add GitLab and Bitbucket tools behind the same `ActivityEvent` interface.
- [ ] Optional LLM-as-judge scoring for prose completeness/faithfulness in the eval harness.
- [ ] Post directly to Slack/Discord once a human approves a non-escalated draft.

---

## License

*This project is contributed under the repository's open-source license (MIT).*
