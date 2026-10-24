# Contribution Reviewer: Pitch

Presented at Road to DevFest: Open Source Edition, GDG Cloud Bengaluru, 24 October 2026.

## 30-second pitch

> Hi, I'm Naveen. This repo had 88 forks on build day, so that's 88 people about to open pull requests, and every one has to pass the same checklist: right folder name, full README, no leaked API keys, nothing changed outside their folder. Checking that by hand is slow for maintainers, and painful for first-time contributors who only find out in review.
>
> So I built **Contribution Reviewer**, an ADK agent on Gemini that reviews your contribution *before* you open the PR. Python checks find the facts, Gemini explains them like a friendly maintainer, and secrets are redacted before the model ever sees them.
>
> Its very first catch? Its own README. That's when I knew it worked.

---

## 2-minute version with live demo

**1. The problem (20 sec)**
> "Open source lives or dies on the first PR. On build day, 88 people forked this repo. Each PR has to pass an eight-item checklist, and maintainers check it all by hand. A first-timer who forgets `.env.example` or leaks a key gets bounced, and some never come back."

**2. The solution (20 sec)**
> "Contribution Reviewer is a Google ADK agent with five tools. They check structure, README completeness, leaked secrets, and whether you touched files outside your folder. The design decision I care about most: **Python decides pass or fail, Gemini only explains.** So the model can't invent problems, and it never sees a real secret."

**3. Live demo (50 sec)**

From the repository root:

```bash
# A good contribution: the reviewer checking itself
python agents/contribution-reviewer/main.py agents/contribution-reviewer --checks-only
#  → 4 × PASS, "Ready for review"

# A lazy contribution: template copied, nothing filled in, a key hardcoded
python agents/contribution-reviewer/main.py ../demo/agents/weather-agent --checks-only
#  → missing .env.example, 8 unfilled README placeholders,
#    a committed .env, and a hardcoded Google key shown redacted as AIza…(39 chars)
```

To build the lazy demo project, make a folder `agents/weather-agent` **outside this repo**, so its fake key can never be committed. Copy `template/README.md` and `template/.gitignore` into it, then add an empty `requirements.txt`, a `.env` file, and a `main.py` containing a fake `AIza...` key.

> "No API key needed for this mode, and it exits non-zero, so it can run on every PR in CI."

**4. Why it matters (20 sec)**
> "It's tested with 14 tests, it's read-only and never runs the reviewed project's code, and it's already a PR to this repo. Next steps: run the AI review fully offline on **Gemma 4 through Ollama**, so your code never leaves your laptop, and a GitHub Action that posts the review on every new PR. Then every contributor after me gets a reviewer on day one."

**5. Close (10 sec)**
> "Build it, document it, open-source it, and now, review it. Thank you!"

---

## Questions and answers

| Question | Answer |
| :--- | :--- |
| *Why not just a linter?* | The checks *are* a linter. The agent adds judgment: "your setup steps skip creating the venv" is something regex can't say. |
| *What about hallucination?* | Pass or fail comes only from the tool results, and the prompt forbids inventing files. When the model wrongly called `gemini-3.8-flash` a typo, it couldn't change the verdict, and one prompt rule fixed it. |
| *Is it safe to run on strangers' PRs?* | Yes. It's read-only, never runs their code, and secrets are redacted before the model sees them. |
| *Why ADK?* | Plain Python functions become tools automatically, and `adk web` gives a chat UI for free. |
| *Why does scope say SKIP in the demo?* | The demo project is outside the repo on purpose, so the fake key can't be committed. Scope needs git history, so it skips instead of guessing. |
| *What's next?* | Gemma 4 through Ollama for a fully offline, private review: the `gemma4:e2b` model supports tool calling, and ADK connects to it through LiteLLM. Then a GitHub Action that comments on PRs, reviewing by PR number, and entropy-based secret detection. |
| *Why not Gemma today?* | It's a 4.3 GB download on event Wi-Fi, so I prioritized a tested, working PR. With ADK, switching models is a one-line config change. |

## The story behind it

On its first real AI run, the agent reviewed itself. It made two good suggestions, which were applied: a setup step that failed when the `upstream` remote already existed, and replacing an illustrative README sample with a real one. It also wrongly called `gemini-3.8-flash` a typo, because the model's training data predates that release.

That's exactly why Python decides pass or fail and the model only explains: the mistake couldn't change the verdict. One prompt rule fixed it, and the next run said "None required for merge."
