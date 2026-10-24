# Invoice Chaser — Product Spec

> Status: **Draft v0.1** · Last updated: 2026-10-24 · Implementation: not started

---

## 1. Problem

Freelancers and small agencies do the work, send the invoice, and then **spend hours chasing payment** — or worse, don't chase at all because it feels awkward. Payments arrive by bank transfer with cryptic references, often short-paid due to TDS, and it's hard to tell at a glance who has actually paid.

The result: late cash flow, forgotten invoices, strained client relationships, and owner time wasted on bookkeeping instead of work.

## 2. Target user

### Primary persona — Priya, independent designer / small agency owner
- 5–20 active clients, mostly Indian businesses, a few international
- Invoices sent as PDF over **email**; paid via **NEFT / IMPS / UPI / wire**
- Indian clients frequently deduct **TDS (typically 10%)** before paying
- Tracks invoices in a spreadsheet; checks bank statements manually
- Relationships matter — losing one client is a big deal, so tone must be careful
- Comfortable with English; many clients prefer **Hinglish** in informal follow-ups

### Job to be done
> *"When a payment is late, help me know exactly who owes what, remind them in the right tone without damaging the relationship, and keep track of what they told me — without me doing bookkeeping."*

### Non-users (v1)
- Large businesses with ERP / AR teams
- High-volume B2C sellers (hundreds of invoices/day)

## 3. User stories (MVP)

| # | As Priya, I want to… | So that… |
|---|---|---|
| U1 | import my invoices from a CSV | I don't re-enter data |
| U2 | paste or import my bank statement | the tool knows what's been paid |
| U3 | have payments auto-matched to invoices, including TDS short-payments | I don't reconcile by hand |
| U4 | confirm matches the tool isn't sure about | wrong matches never silently corrupt my books |
| U5 | see a "chase today" list ranked by priority | I know where to focus |
| U6 | get reminder drafts in the right tone (friendly → firm) | I don't agonise over wording |
| U7 | get drafts in English or Hinglish per client | messages feel natural |
| U8 | approve, edit, soften/firm-up or skip each draft | nothing goes out without my say |
| U9 | paste a client's reply and have the tool understand it | promises and disputes are tracked automatically |
| U10 | be reminded when a client breaks a promise | follow-ups don't slip |
| U11 | see a full history of what the agent did and why | I can trust and audit it |

## 4. Product components

| ID | Component | Purpose | MVP? |
|---|---|---|---|
| A | **Invoice Book** | Source of truth for invoices, amounts, due dates, status | ✅ |
| B | **Client Profile** | Contact, language, tone preferences, relationship flags, history | ✅ (basic) |
| C | **Payment Inbox & Matching** | Ingest bank lines; match to invoices with confidence levels | ✅ |
| D | **Collections Dashboard** | Outstanding totals, ageing buckets, ranked chase list | ✅ (CLI view) |
| E | **Reminder Engine** | Tone-ladder drafts, personalised, policy-checked | ✅ |
| F | **Approval Queue** | Human approves / edits / skips every outgoing message | ✅ |
| G | **Response Handling** | Classify replies → promise / dispute / claims-paid / etc. | 🎯 Stretch (cut for 1-day build; design kept) |
| H | **Reports & Insights** | Weekly digest, client payment behaviour | ⏳ v2 |
| I | **Guardrails & Audit** | Grounding, policy limits, full audit trail | ✅ (always) |

### Tone ladder (E)

| Level | Name | Typical trigger | Character |
|---|---|---|---|
| 0 | Heads-up | 3 days before due | Warm, informational |
| 1 | Gentle nudge | 1–7 days overdue | Friendly, assumes oversight |
| 2 | Firm reminder | 8–30 days overdue or 1 broken promise | Polite, direct, asks for a date |
| 3 | Final notice | 30+ days or 2 broken promises | Formal, states next steps the owner configured |

Escalation is **never automatic past level 2** without Priya's opt-in per client. Relationship flags (e.g. `gentle`) cap the level.

### Lifecycle states

- **Invoice:** `SENT → DUE → OVERDUE → PARTIALLY_PAID → PAID`, plus `DISPUTED`, `WRITTEN_OFF`
- **Reminder:** `DRAFTED → QUEUED → APPROVED → SENT → RESPONDED` (or `DROPPED` by policy / `SKIPPED` by owner)
- **Promise-to-pay:** `ACTIVE → KEPT | BROKEN`

## 5. Key user journeys

1. **Daily chase run** — import payments → auto-match → review uncertain matches → see chase list → review drafts → send manually → mark sent.
2. **Reply handling** — paste client reply → agent classifies → proposes action → Priya confirms → state updated, reminders paused/resumed accordingly.
3. **Broken promise** — promised date + grace passes without payment → next chase run drafts a follow-up referencing the promise, one tone level higher.

## 6. Scope

### In (MVP)
- CLI interface
- CSV invoice import; CSV / pasted-text bank payment import
- INR primary; foreign currency invoices stored but matched only on exact-currency lines
- Email-style drafts (subject + body), English + Hinglish
- *Stretch:* paste-in reply classification (G) and promise tracking
- Mock model for the test suite, so tests run without an API key

### Out (MVP) — explicit non-goals
- **Sending** emails/WhatsApp automatically (owner sends; we only draft)
- Live bank / inbox integrations
- PDF / photo invoice OCR
- Legal notices, interest calculation, collections-agency handoff
- Multi-user / multi-business

## 7. Success metrics

| Metric | Why it matters | MVP target (on eval set) |
|---|---|---|
| Auto-match precision | Wrong matches corrupt books | ≥ 99% |
| Auto-match coverage | Saves owner effort | ≥ 80% of matchable lines |
| Draft accept-without-edit rate | Proxy for draft quality | ≥ 70% |
| Reply intent accuracy | Drives correct state changes | ≥ 90% |
| Factual errors in sent drafts | Trust killer | **0** (structurally enforced) |
| Time to complete daily run | Owner time saved | < 5 min for 20 clients |

Real-world (post-hackathon): reduction in Days Sales Outstanding (DSO), ₹ recovered after reminders.

## 8. Decision log

| Date | Decision | Rationale |
|---|---|---|
| 2026-10-24 | Primary persona = freelancer / small agency (Priya) | Fewer, higher-value invoices; email channel; tone sensitivity makes the agent's judgement valuable |
| 2026-10-24 | Response Handling in MVP (paste-in only) | Most "agentic" part; low volume for this persona keeps scope small |
| 2026-10-24 | Hinglish drafts in MVP | Strong differentiator for Indian context |
| 2026-10-24 | Draft-only, never send | Outward-facing actions to real clients must stay human-controlled |
| 2026-10-24 | Ledger tool lives inside this agent's folder | Keeps the PR scoped to one directory per CONTRIBUTING.md |
| 2026-10-24 | Stack: Python + Google ADK + Gemini (AI Studio key) | Team choice; AI Studio free tier keeps setup reproducible for reviewers |
| 2026-10-24 | Build time is 1 day → Response Handling (G) moved to stretch | Protect reliability of the core loop (match → chase list → drafts → approval) over breadth |
| 2026-10-24 | TDS rates configurable, default 10% | 10% covers professional fees (Sec 194J); others added via config |
| 2026-10-24 | Solo build; Hinglish kept in MVP | Low cost (prompt-level language option + a few eval cases), high differentiation; remains second in the cut order |
| 2026-10-24 | Sample data: synthetic "Priya Design Studio" (~8 clients, ~12 invoices) | No real client data in an open-source repo |

## 9. Open questions
- Should Priya be able to set a per-client "do not chase before day N" rule in v1?
- Grace period after a promise date — fixed 2 days or configurable? (only matters once G is built)
