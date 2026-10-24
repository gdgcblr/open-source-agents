# Namma Commit 🤝

*Your first open-source PR, in your language.*

Namma Commit ("our commit") is the **Newcomer Coach**, the student-facing side of **Maintainer Copilot**. The gatekeeper helps maintainers review pull requests;
Namma Commit helps students and first-timers *make* their first good one. They chat on WhatsApp, in
any language, by text or voice note.

It is a Google ADK multi-agent backed by Gemini. Everything that matters for safety or fairness is
deterministic code: points, PR verification, file writes, secret detection and pre-flight checks.

## What a student sees

```
Student: नमस्ते                                   (any language, text or voice)
Coach:   welcome + privacy note + 3 questions (language? skills? time per week?)
Student: answers                                -> save_profile
Coach:   3 recommendations: event challenges (challenges.yaml) + good-first issues from allowlisted repos
Student: "2"                                    -> choose_issue
Coach:   explains like a mentor, asks back: "what do you think causes it? which file would you change?"
Student: explains the fix (text or 🎙️ voice)    -> solution_drafter (FixPlan) -> save_fix_plan
Coach:   FIX_PLAN.md + draft file attached, +10 points, gatekeeper pre-flight findings to fix first
Student: "how do I submit?"                     -> pr_guide: fork -> clone -> branch -> copy -> commit -> push -> PR
                                                   one step per message, exact commands for their OS
Student: https://github.com/.../pull/42         -> verified with the GitHub API -> +20 (and +50 when merged)
                                                -> FINAL STEP, in the background: MergeWarden (the maintainers'
                                                   gatekeeper) reviews the PR against CONTRIBUTING.md
Coach:   (a minute later) ✅/🛠️/⛔ verdict + score, what's good, top 3 fixes with the CONTRIBUTING rule,
         all in the student's language. "Push to the same branch, then send 'review again'."
```

The final step closes the loop between the two halves of Maintainer Copilot. The student gets the same
review a maintainer will see, explained like a mentor would, and can fix everything before a human spends
time on it. A "ready" verdict earns the ✅ Clean PR badge.

## Architecture

```
 WhatsApp ──Twilio──► POST /twilio/webhook ─┐
 Web simulator ─────► POST /api/message ────┼─► service.handle_message(user_id, text, audio, mime)
 Terminal ──────────► coach chat ───────────┘        │
                                                     │ 1 hash id  2 rate/size limits  3 voice -> transcript
                                                     │ 4 commands  5 secret refusal  6 redact + injection flag
                                                     │ 7 PR link -> GitHub API verify   8 <untrusted> wrap
                                                     ▼
                         coach_agent (LlmAgent coordinator: leaderboard, points, verify_pr)
                         ├─ onboarding_agent   save_profile
                         ├─ issue_scout        list_challenges, search_good_first_issues, choose_issue
                         ├─ mentor_explainer   AgentTool(solution_drafter -> FixPlan), save_fix_plan,
                         │                     run_preflight_checks, award_points
                         └─ pr_guide           pr_steps, verify_pr
                                                     │
                                                     │
                     verified PR link -> review.py: cli.review(PR) in a worker thread (CONTRIBUTING.md policy,
                     deterministic checks, Gemini doc/policy reviewers) -> coach explains it -> notify / inbox
                                                     │
                     store.py (sqlite): users (hashed id) · append-only points ledger · badges · last 20 redacted turns
                     drafts: COACH_DATA_DIR/drafts/<user_hash>/<issue>/   (never inside a repository)
```

| File | What it does |
| --- | --- |
| `agent.py` | `coach_agent` and its sub-agents, instructions, `FixPlan` schema |
| `service.py` | `handle_message` pipeline, voice transcription, sessions, `CoachReply` |
| `tools.py` | deterministic tools: profile, issues, points, PR verification, drafts, pre-flight, PR steps |
| `guardrails.py` | hashing, secret/injection detection, redaction, rate limit, audio limits, sandbox paths |
| `store.py` | sqlite users, ledger, badges, transcript |
| `review.py` | final step: runs the gatekeeper review on the student's PR, summarises it for the coach |
| `llm.py` | Gemini with automatic fallback model on 429/5xx |
| `whatsapp.py` | Twilio webhook signature check, media download, TwiML, async REST replies |
| `server.py`, `static/` | FastAPI app: simulator, leaderboard page, webhook, signed draft links |
| `challenges.yaml` | event challenges maintainers curate |

## Run it

From `agents/mergewarden/` with the project venv and a Gemini key in `.env` (`GOOGLE_API_KEY=`):

```bash
.venv/bin/python -m mergewarden.coach serve       # http://localhost:8090
```

- `http://localhost:8090/` is a WhatsApp look-alike simulator: chat bubbles, language tag on every reply,
  a 🎤 button that records a voice note in the browser, points/badge toasts, and draft files as attachments.
  "New student" starts a fresh identity. No accounts needed.
- When a review finishes, the simulator picks it up from `/api/inbox` (polled every 4 s) and shows a
  verdict chip on the message. Over WhatsApp it is sent through the Twilio REST API. In `chat` it is printed.
- `http://localhost:8090/leaderboard` is the public leaderboard (GitHub handles or pseudonyms only).

Fastest demo, text only:

```bash
.venv/bin/python -m mergewarden.coach chat
```

Commands that work in any channel: `leaderboard` (or `top`), `my points`, `review again`, `restart`, `help`,
`delete my data`. The coach also understands these in any language and calls the matching tool.

Tests (offline, fake model):

```bash
.venv/bin/python -m pytest -q tests/test_coach*.py
```

## Connect real WhatsApp (Twilio Sandbox + ngrok)

1. Create a free Twilio account. In the console open **Messaging → Try it out → Send a WhatsApp message**.
   Join the sandbox from your phone by sending the shown `join <code>` message to the sandbox number.
2. Expose the local server:
   ```bash
   ngrok http 8090
   ```
   Copy the `https://….ngrok-free.app` URL.
3. Add to `.env`:
   ```
   TWILIO_ACCOUNT_SID=ACxxxxxxxx
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
   PUBLIC_BASE_URL=https://xxxx.ngrok-free.app
   COACH_SALT=a-long-random-string
   ```
4. In the sandbox settings set **When a message comes in** to `https://xxxx.ngrok-free.app/twilio/webhook` (HTTP POST).
5. Restart `serve` and send "hi" from WhatsApp. Voice notes work the same way.

`PUBLIC_BASE_URL` must be exactly the URL Twilio calls: the signature is computed over it, and requests
with a missing or wrong `X-Twilio-Signature` are rejected with 403. If a reply takes longer than ~11 s, the
webhook answers with an empty TwiML and the reply is sent through the Twilio Messages REST API instead.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `GOOGLE_API_KEY` | (required) | Gemini API key |
| `GATEKEEPER_COACH_MODEL` | `gemini-3.8-flash` | coach model (thinking level low) |
| `GATEKEEPER_COACH_FALLBACK_MODEL` | `gemini-3.5-flash-lite` | used automatically on 429/5xx |
| `COACH_REPOS` | `gdgcblr/open-source-agents` | comma-separated allowlist of repos for issues and PR points |
| `COACH_DATA_DIR` | `./.coach-data` (project folder) | sqlite files and draft sandbox; gets its own `.gitignore` |
| `COACH_SALT` | empty | salt for hashing phone numbers; also signs draft links. **Set it in production.** |
| `COACH_PORT` | `8090` | `serve` port |
| `COACH_RATE_LIMIT_MSGS` / `COACH_RATE_LIMIT_WINDOW_S` | `20` / `600` | messages per user per window |
| `COACH_MAX_AUDIO_BYTES` / `COACH_MAX_AUDIO_SECONDS` | `5242880` / `120` | voice note limits |
| `COACH_MAX_TEXT_CHARS` | `2000` | longer messages are truncated |
| `COACH_MAX_TURNS_PER_SESSION` | `60` | then a fresh model context starts (profile and progress kept) |
| `COACH_DAILY_POINT_CAP` | `100` | max points per user per UTC day |
| `COACH_REVIEW_USE_LLM` | `1` | include the gatekeeper's Gemini reviewers in the final review (`0` = deterministic only) |
| `COACH_REVIEW_TIMEOUT_S` | `600` | max time for one PR review |
| `COACH_REVIEW_COOLDOWN_S` | `300` | wait before the same PR can be reviewed again |
| `COACH_MAX_REVIEWS_PER_DAY` | `5` | reviews per student per UTC day |
| `COACH_REVIEW_CONCURRENCY` | `2` | reviews running at once (each clones the PR) |
| `GATEKEEPER_MODEL` | `gemini-flash-latest` | model used by the gatekeeper reviewers (existing setting) |
| `GITHUB_TOKEN` | optional | not needed if the `gh` CLI is logged in (`gh auth login`): the coach uses its token automatically (5000 req/h instead of 60) |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, `PUBLIC_BASE_URL` | empty | WhatsApp only |

## Guardrails & security

**Untrusted input.** Student messages, voice transcripts, GitHub issue bodies and repo content are data, not
instructions. Each is wrapped in `<untrusted source="…">` tags (closing tags inside are escaped), and every
agent's instruction says never to follow instructions found inside them. The gatekeeper's own
`checks.injection.scan` plus coach-specific patterns ("award me 500 points", "reveal your prompt") flag
attempts. A flagged message still gets a kind answer, but the model is told about the attempt for that
turn, and it can't do anything harmful anyway because the dangerous actions are deterministic tools.

**Secrets.** The coach never asks for passwords, OTPs, tokens or keys. Each message is scanned with the
gatekeeper's `checks.secrets.VENDOR_PATTERNS`, its generic high-entropy rule, and a password/OTP pattern.
On a hit the coach refuses in the student's language, tells them to delete the message and rotate the
credential, and **neither stores the message nor sends it to the model**. Drafts are scanned again
by pre-flight before the student sees them.

**Privacy.**
- Only `sha256(phone + COACH_SALT)` is stored. The phone number stops at the first line of `handle_message`.
- Phone numbers and emails are redacted before text is stored or sent to the model.
- Voice notes go to Gemini once for transcription, then the bytes are dropped. Only the transcript is
  kept, and it is redacted like any message.
- Only the last 20 redacted turns per student are kept, to resume after a restart.
- The consent message on first contact covers all of this, and says messages are processed by Google Gemini.
- `delete my data` erases the profile, ledger rows, badges, transcript, drafts and model session immediately.

**Abuse limits.** 20 messages per 10 minutes per user, voice notes up to 5 MB and 2 minutes (the browser
stops at 2 minutes and the server checks again), 2000 characters per message, a fresh model context every
60 turns, and polite refusal of off-topic or harmful requests (the coach only does open-source learning).
One turn per student runs at a time.

**No code execution, ever.** No agent has a code executor. The coach never runs, pushes or merges code
and never opens PRs. The student does every git step. Drafts are written only to
`COACH_DATA_DIR/drafts/<user_hash>/<issue>/`. Each path component must be a plain name, file
extensions are allowlisted, and the resolved path must stay inside the sandbox, so traversal is refused.
Draft download links are HMAC-signed and resolve only inside the drafts folder.

**Final-step review.** It runs only for a PR that passed verification (exists, is in an allowlisted repo, and
was authored by the student's registered handle). The gatekeeper snapshots the PR with `git archive` into a
temp folder and never executes it. Reviews are capped by a timeout, a global concurrency limit, a per-PR
cooldown and a daily per-student limit. The coach gets the verdict and score as trusted facts, but the
finding texts (which can quote the PR) go inside `<untrusted>` tags, and it is told never to change the
verdict or invent findings. The coach never posts the review on GitHub: that stays the maintainers' choice
(`python -m mergewarden review --post`).

**Allowlists.** Issues, challenges and PR points come only from `COACH_REPOS`. Twilio media is fetched
only from Twilio hosts, with a size cap while streaming.

**Anti-gaming.**
- Points come only from deterministic tools. The model can't grant them, and a student can't talk it into
  them.
- PR points (20) and merge points (50) are paid only after the GitHub API confirms the PR exists, targets an
  allowlisted repo, and was authored by the GitHub handle the student registered. Merges need `merged=true`.
- Bug-report and clarification points also need a GitHub link written by that handle.
- Every award has a unique event key, so the same event never pays twice. GitHub events (PRs, merges,
  issues, comments) pay once across all users, and each GitHub handle can be registered by only one student. A daily cap applies, and an
  award over the cap is not recorded, so it can be claimed the next day.
- The ledger is append-only (an sqlite trigger aborts any `UPDATE`) and every row carries its reason and
  evidence link.

**Tone.** Instructions require a warm, encouraging, never-shaming mentor voice that suits students and
kids, short WhatsApp-sized messages, and Socratic questions before solutions.

## Points & badges (no money, ever)

| Event | Points | Verified by |
| --- | --- | --- |
| Report a bug | 5 | GitHub issue authored by the student's handle |
| Clarify an issue | 5 | GitHub comment authored by the student's handle |
| Submit a FIX_PLAN | 10 | the plan is generated and saved in the sandbox |
| Open a PR | 20 | GitHub API: PR exists, allowlisted repo, author matches |
| PR merged | 50 | GitHub API: `merged=true` |

Badges: 🌱 First Steps (first points), 🗣️ Polyglot (chatted in 2+ languages), 🐞 Bug Hunter (bug report),
📚 Docs Hero (docs challenge plan/PR), 🏆 Merged! (merged PR).

## Known limitations

- Without `sqlalchemy` installed, ADK sessions are in memory. A restart keeps the profile, chosen issue,
  points and the last redacted turns (from our sqlite store), but the model's detailed context is
  summarised. Install `google-adk[db]` to get sqlite-backed ADK sessions automatically.
- The rate limiter is in-process memory, so it resets on restart and doesn't span multiple server instances.
- Voice-note length on the server is estimated from size (compressed audio stays under 128 kbit/s). An
  uncompressed WAV is only limited by the 5 MB cap.
- Language detection for fixed messages is by script (Devanagari = Hindi, and so on). Marathi or Nepali
  in Devanagari are labelled Hindi, but the model still replies in the student's actual language.
  Romanised languages other than Hinglish are labelled English.
- Fixed system messages (secret refusal, rate limit, deletion, errors) are translated into English, Malayalam,
  Hindi and Kannada only. Every other reply is generated in whatever language the student uses.
- The coach doesn't send files over WhatsApp. It sends HMAC-signed links when `PUBLIC_BASE_URL` is set.
  Anyone holding a link can read that draft until the server restarts (or forever if `COACH_SALT` is fixed).
- Pending deliveries (the simulator inbox and the per-student WhatsApp callback) live in process memory.
  A restart while a review is running loses that one delivery. The result is still saved, so
  `review_status` or "review again" recovers it.
- A PR review clones the repo into the gatekeeper cache (`~/.cache/mergewarden`), so the first
  review of a repo is slower.
- GitHub handle ownership isn't proven (no GitHub OAuth). The first student to register a handle owns it
  for points. A maintainer can resolve disputes with `delete my data` on the wrong account.
- Without `gh auth login` or `GITHUB_TOKEN`, GitHub's anonymous limit is 60 requests/hour. That's too low for an event.
- Voice audio is sent to Google Gemini for transcription, so it leaves the machine once.
