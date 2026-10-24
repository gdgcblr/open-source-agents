# First PR Mentor

> A terminal mentor for first-time open source contributors: it finds open issues in your tech stack that are likely to get merged, explains the repo and the issue in plain words, checks that you understand it, and only then gives you a PR checklist and draft. You still write and open the PR yourself.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: New contributors don't know *where* to contribute or *how*. Beginner-issue lists show thousands of issues but not which ones are already claimed, already have a PR, or sit in repos that never merge outsider PRs. Many newcomers then paste the issue into an AI, submit code they don't understand, and get closed. In 2026 maintainers are overwhelmed by this: a Linux Foundation survey found maintainers estimate about 25% of incoming PRs are low-quality AI submissions, and GitHub added caps on how many PRs outsiders can keep open.
- **Intended Users**: Students and developers making their first 1–10 open source contributions, and the community leads who mentor them.

### Use Cases
| Who | Situation | What First PR Mentor does |
| :--- | :--- | :--- |
| **A student making a first PR** | "I know React and TypeScript, but where do I even start?" | Runs `find --stack "react, typescript"` and gets ranked, still-open issues from repos that actually merge outsider PRs, with reasons |
| **A bug hunter short on time** | Doesn't want to fix something that someone else already has a PR for | Issues with an assignee, an open PR, or a recent "can I take this?" claim are marked SKIP or flagged before any time is spent |
| **A newcomer facing a huge repo** | A monorepo with 4,000 files and no idea where the code lives | `learn` gives a folder map, setup commands, the issue in plain words, and which files to open, in Kannada or Hindi if preferred |
| **Someone tempted to paste the issue into AI** | Would submit code they can't explain | Must answer 3 questions in their own words before the PR kit unlocks. The mentor gives hints, never the fix |
| **A community lead running a hackathon** (like FORK. BUILD. MERGE.) | 100 students, few mentors | Every student gets the same step-by-step path and a PR checklist built from each repo's real rules, so maintainers get fewer rejected PRs |

**Real example from 2026-10-24:** for `react, nextjs, typescript` the top pick was `mattermost/mattermost#18579` (89/100): a maintainer said PRs are welcome, and 22 of the last 23 outsider PRs were merged, usually within 2 days. Meanwhile video.js "good first issues" were flagged as stale for over 1,200 days, and one links to a file that was deleted in a rewrite.

### Key Features
- **Find, ranked by chance of merge**: searches GitHub for active repos in your stack, then scores each beginner issue from live data. It reads the issue *conversation* (claims like "can I work on this?", maintainer replies, "PRs welcome") and the repo's recent PR history (outsider merge rate, time to merge, first-timer merges). Every score shows its reasons.
- **Skips dead ends automatically**: issues that are assigned, already referenced by an open PR, stale for a year, or labelled "needs discussion".
- **Explains complex repos simply**: Gemini turns the README, file tree, contributing guide and issue thread into a folder map, setup steps, the issue in plain words, the likely files to change, and the concepts to learn first. File paths are checked against the real repo, so a made-up path is marked as an AI guess.
- **Understanding check**: three questions about the issue, graded in your own words, with hints instead of answers. You need 2 of 3 to unlock the PR kit.
- **PR kit from the repo's real rules**: a checklist built from `CONTRIBUTING.md` and the PR template (sign-off, CLA, Conventional Commits, tests, changesets, base branch, AI policy), each item quoting the sentence it came from, plus a PR description seeded with *your* answers and an AI-assistance disclosure.
- **"Is it still available?" check**: before teaching you an issue, it checks for assignees, open PRs, claims in comments, staleness, and files the issue links to that no longer exist (a sign the code was rewritten).
- **Your language**: `--lang kannada` (or hindi, tamil, …) makes Gemini explain and give feedback in that language, keeping code and commands in English.
- **Works without keys**: `--offline` (or no Gemini key) explains from the repo files with no AI and never invents a file path. `--demo` replays a recorded GitHub run, so reviewers can try it with no token and no network to GitHub.

---

## Technical Stack
- **Language & Runtime**: JavaScript (ES modules), Node.js 20.12+
- **Agent Framework / Core Library**: Vanilla Node.js (no npm dependencies)
- **Models**: Google Gemini via the Gemini REST API (default `gemini-3.8-flash`, configurable)
- **External APIs / Tools**: GitHub REST API (read-only)

---

## Architecture & Data Flow

```
 You: "react, nextjs, typescript"
        │
        ▼
 ┌──────────────┐   GitHub search (topic + language + good-first-issues + pushed recently)
 │ 1. FIND      │──► per repo: last 50 closed PRs, community profile, beginner labels
 │  (no AI)     │──► per issue: comments + timeline (claims, open PRs, maintainer replies)
 └──────┬───────┘   scoring.js → score 0-100 + reasons → GOOD / MAYBE / RISKY / SKIP
        ▼
 ┌──────────────┐   README + file tree + CONTRIBUTING + issue thread
 │ 2. EXPLAIN   │──► Gemini (GitHub text wrapped as <untrusted> data)
 │  (Gemini)    │   → folder map, setup, issue in plain words, likely files (verified), concepts
 └──────┬───────┘
        ▼
 ┌──────────────┐
 │ 3. CHECK     │──► 3 questions, answers graded by Gemini, hints not solutions
 └──────┬───────┘   pass 2/3 to continue
        ▼
 ┌──────────────┐   rules.js: keyword detectors on CONTRIBUTING + PR template (no AI)
 │ 4. PR KIT    │──► checklist with quoted evidence + PR draft from your answers
 └──────┬───────┘
        ▼
 mentor-sessions/<owner>__<repo>-<issue>.md   (you open the PR yourself)
```

Scoring and rule detection are plain code, so the same input always gives the same result. Only explanations and grading use the model.

---

## Prerequisites
- Node.js 20.12 or newer (`node --version`)
- A Gemini API key (free tier available at [Google AI Studio](https://aistudio.google.com/apikey)), needed for `learn`, `explain` and `start`
- Recommended: a GitHub personal access token with **no extra permissions** (public, read-only)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/first-pr-mentor
   ```

2. **Install dependencies:** there are none. `npm install` is not required (the `package.json` has no dependencies).

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Then put your keys in `.env`.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes for `learn`/`explain`/`start` | *None* | Gemini API key from Google AI Studio |
| `GEMINI_MODEL` | No | `gemini-3.8-flash` | Any Gemini model that supports `generateContent` (e.g. `gemini-3.5-flash-lite`) |
| `GITHUB_TOKEN` | Recommended | *None* | Read-only token. Without it GitHub allows 60 requests/hour, about one `find` run |
| `NO_COLOR` | No | *unset* | Set to `1` to disable colored output |

---

## How to Run

```bash
# Guided mode: asks your stack, finds issues, teaches you the one you pick
npm start

# Only rank issues (works without a Gemini key)
node src/cli.js find --stack "react, nextjs, typescript"

# Learn an issue from your last search by its number, or by reference
node src/cli.js learn 1
node src/cli.js learn tldraw/tldraw#1234

# Only the explanation, no quiz
node src/cli.js explain tldraw/tldraw#1234

# Explain in Kannada
node src/cli.js learn tldraw/tldraw#1234 --lang kannada

# Try it with no keys and no GitHub access (replays a recorded run)
node src/cli.js learn videojs/video.js#1169 --demo
```

Options: `--level beginner|intermediate`, `--lang <language>`, `--repos <n>` (repos to check, default 4), `--offline` (no AI), `--demo` (recorded GitHub data), `--verbose` (show every GitHub request).

| Mode | Needs | What you get |
| :--- | :--- | :--- |
| `--demo` | nothing | Replays GitHub data recorded on 2026-10-24: `find --stack "react, nextjs, typescript"` and `learn videojs/video.js#1169` |
| `--offline` / no Gemini key | GitHub access (token recommended) | Live find + availability check + explanation from repo files + PR checklist. No quiz |
| full | `GEMINI_API_KEY` + GitHub token | Everything, including the AI explanation and the understanding check |

---

## Example Input & Output

### Example Input
```bash
node src/cli.js find --stack "react, nextjs, typescript"
```

### Example Output
Real run on 2026-10-24 with a GitHub token (shortened; replay it with `--demo`):
```
Finding beginner issues for: react, nextjs, typescript

[1] GOOD PICK 89/100  mattermost/mattermost#18579  ★39419
    RHS Search Results: View Thread link button
    ✔ A maintainer has replied in the thread (1 comment(s))
    ✔ Maintainers signal that PRs are welcome
    ✔ 22 of the last 23 closed PRs from outside contributors were merged (96%)
    ✔ Last PR merged today
    ✔ Outsider PRs usually merge in about 2 day(s)
    ✔ Has a CONTRIBUTING guide

[3] GOOD PICK 71/100  tldraw/tldraw#8880  ★51063
    Restore help menu in bottom-right corner and replace sidebar help menu with user menu
    ! @ravvdevv asked to work on it 131 days ago with no PR: politely ask if it's still taken
    ✔ 13 of the last 14 closed PRs from outside contributors were merged (93%)
    ! Outsider PRs usually merge in about 20 day(s)

[6] MAYBE 60/100  videojs/video.js#1169  ★40005
    Html5 src behaves incorrectly
    ! @c0rdial asked to work on it 1126 days ago with no PR: politely ask if it's still taken
    ✘ No activity for 875 days: may be outdated or forgotten
```

An earlier anonymous run (no token) marked two other video.js issues **SKIP** because open PRs already reference them:
```
[2] SKIP 0/100  videojs/video.js#7736  ★40004
    ✘ An open PR already references it (#9177)
```

### Example: `learn` without a Gemini key
Real run on 2026-10-24 (replay it with `--demo`), shortened:
```
$ node src/cli.js learn videojs/video.js#1169
Offline mode (no GEMINI_API_KEY in .env): explaining from the repo files only, no AI and no quiz.

🚦 Is #1169 still available?
  ! @c0rdial asked to work on it 1126 days ago with no PR: politely ask if it's still taken
  ✔ A maintainer has replied in the thread (7 comment(s))
  ✘ No activity for 875 days: may be outdated or forgotten
  ✘ The issue links to `src/js/media/html5.js`, which no longer exists: the code was probably moved or rewritten

📦 videojs/video.js: what it is
Video.js v10 - open source media player framework for HTML and React. ...
Tech: TypeScript, Node.js, Vite, React (JSX), pnpm workspaces

🗺️  Folder map
  .github/                 GitHub settings: CI workflows, issue and PR templates
  apps/                    Monorepo: each sub-folder is its own package or app
  packages/                Monorepo: each sub-folder is its own package or app
  site/                    Documentation

▶️  How to run it
  1. git clone https://github.com/{your-github-username}/video.js.git
  2. cd video.js
  3. pnpm install
  4. pnpm build:packages
  5. pnpm dev

✅ Your PR checklist
  [ ] Comment on the issue that you'd like to work on it, and wait for a maintainer's OK
  [ ] Fork videojs/video.js and create a branch: `git checkout -b fix/1169-html5-src-behaves-incorrectly`
  [ ] Use Conventional Commit messages (feat:, fix:, docs:)
      from CONTRIBUTING.md: "1. [release-please][release-please] keeps a release PR open on `main`, built from conventional commits. ..."
  [ ] Run the linter/formatter before pushing
      from CONTRIBUTING.md: "pnpm lint                    # check the whole workspace"
  [ ] Link the issue in the PR description ("Fixes #1169")
  [ ] Read your own diff line by line; you must be able to explain every change
```
### Example: Gemini explanation in Kannada
Real run on 2026-10-24 with `GEMINI_MODEL=gemini-3.5-flash-lite` (shortened):
```
$ node src/cli.js explain videojs/video.js#1169 --demo --lang kannada
Asking gemini-3.5-flash-lite to explain it for a beginner in kannada…

📦 videojs/video.js: what it is
Video.js ಒಂದು ಪ್ರಸಿದ್ಧ ಓಪನ್ ಸೋರ್ಸ್ ಮೀಡಿಯಾ ಪ್ಲೇಯರ್ ಫ್ರೇಮ್ವರ್ಕ್. ...
Tech: TypeScript, React, HTML, Node.js, pnpm, Playwright

🗺️  Folder map
  packages/core/           ಇದು ಪ್ಲೇಯರ್‌ನ ಮುಖ್ಯ ಕೋಡ್ ಅನ್ನು ಹೊಂದಿದೆ.
  apps/sandbox/            ಇದು ಪರೀಕ್ಷಿಸಲು ಮತ್ತು ಪ್ರಯೋಗ ಮಾಡಲು ಒಂದು ಸ್ಯಾಂಡ್‌ಬಾಕ್ಸ್ ಅಪ್ಲಿಕೇಶನ್.

🔎 Where to look
  ? packages/core/: ... (not found in repo: AI guess)

📚 Concepts to learn first
  • Getter and Setter: ...
  • Monorepo: ...
```
The path check flagged Gemini's suggestion `packages/core/` because it is a folder, not a real file. Learners can see what is verified and what is a guess. During testing `gemini-3.8-flash` returned `503 high demand`; set `GEMINI_MODEL=gemini-3.5-flash-lite` if that happens.

The verdict here is honest: this "good first issue" looks open, but the mentor shows it is stale and points at code that was rewritten, so a beginner should pick another one.

---

## How to Test

```bash
npm test
```

22 offline unit tests (Node's built-in test runner, no network, no keys) cover:
- repo scoring: welcoming vs. closed repos, bot PRs excluded from merge rate, archived repos
- issue scoring: assigned and already-PR'd issues blocked, claims in comments, maintainer invitations, staleness
- rule detection from a sample `CONTRIBUTING.md` and PR template
- stack parsing, beginner-label ranking, issue references
- prompt-injection wrapper and the PR kit (issue link, template sections, AI disclosure)
- offline explainer: real file paths only, setup commands from code blocks, stack detection, links to files that no longer exist

Manual check with no keys at all:
```bash
node src/cli.js learn videojs/video.js#1169 --demo
```
Then run `find` live (GitHub token recommended), and `learn 1` with a Gemini key.

---

## Known Limitations
- **"Chance of merge" is a heuristic**, built from the last 50 closed PRs and the issue thread. It is not a prediction model and can't see private maintainer decisions.
- **The model only sees part of the repo**: README, file tree, contributing guide and the issue thread, not the source code. Explanations can be wrong; suggested files are verified to exist but not verified to be the right ones.
- **Rule detection is keyword-based**: it catches common rules (sign-off, CLA, Conventional Commits, tests, changesets, lint, base branch, AI policy) but can miss rules phrased unusually.
- **GitHub rate limits**: without a token you get about one `find` run per hour. Search is limited to 10–30 requests per minute.
- **Search scope**: one search per topic, first matching repos only. It does not cover all of GitHub.
- **Fine-grained GitHub tokens hide "PR mentioned this issue" events** in the issue timeline (found in testing: the same issue showed 3 linked PRs anonymously and 0 with a fine-grained token). With such a token, an issue that already has an open PR may not be marked SKIP. A classic read-only token, or no token, avoids this. A search-based backup check is planned.
- **A recent claim lowers the score but doesn't force a SKIP**: an issue someone asked for in the last 30 days can still rank as a good pick if the repo is very welcoming. Always read the ✘ lines.
- **Offline mode is shallow**: without Gemini it can only match file names to the issue title, and there is no understanding check.
- **Demo data is a snapshot** from 2026-10-24 (`fixtures/demo-github.json`): `find --stack "react, nextjs, typescript"` and `learn videojs/video.js#1169`. Other commands with `--demo` fail with a clear message.
- **Non-English output** depends on Gemini's quality in that language; it was not reviewed by native speakers.
- Tested on Windows 11 with Node 24. macOS/Linux untested but no platform-specific code is used.

---

## Security & Privacy Considerations
- **Secrets Handling**: keys are read from `.env` (git-ignored) via `process.loadEnvFile`. They are never printed, logged or written to session files. The GitHub token only needs public read access.
- **Read-only on GitHub**: the GitHub client only sends `GET` requests. The tool never comments, forks, assigns, or opens PRs for you.
- **Data Privacy**: public repo content and your quiz answers are sent to the Gemini API. Nothing else leaves your machine. Session notes are saved locally in `mentor-sessions/` (git-ignored).
- **Prompt injection**: issue text, comments and READMEs are wrapped in `<untrusted>` tags (with tag spoofing stripped) and the model is told to treat them as data. The model has no tools, so injected text cannot trigger actions.
- **No code execution**: the tool never runs code from the repos it reads.
- **Anti-slop by design**: the mentor gives hints, never full patches, and the PR draft includes an AI-assistance disclosure.

---

## Future Improvements
- [ ] MCP server mode, so coding agents run the merge check before opening PRs
- [ ] Use GitHub GraphQL to read more PR history in fewer requests
- [ ] Cache GitHub responses between runs
- [ ] Track your contributions over time ("next issue" suggestions after your first merge)
- [ ] Local models via Ollama
- [ ] Rebuild the learn flow on Google ADK with GitHub tools the agent can call

---

## License
*This project is contributed under the repository's open-source license.*
