# card-rewards-optimizer

> A grounded Gemini agent that maximizes the value of Indian credit-card reward points and warns you before they expire — where every figure comes from deterministic Python, never the model.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Indian credit-card holders lose reward value two ways — points expire unused, and points get redeemed through poor routes (statement credit at ~0.25 ₹/pt when a transfer partner yields 1.0+ ₹/pt). No open tool reasons over Indian transfer-partner economics.
- **Intended Users**: cardholders comfortable with a CLI, and developers who want a worked example of a function-calling agent whose numbers are provably grounded.

### Key Features
- **Deterministic valuation engine** — every ₹ figure is computed in `engine.py` from a curated rates dataset; the LLM never produces a number.
- **Expiry radar** — reports points expiring in the next 30/60/90 days with the best use of each, and works with **no API key**.
- **Numbers-free `optimize` narration** — the model writes only the qualitative recommendation (which route wins and why); the table beneath it carries every figure, so a wrong number is structurally impossible rather than caught after the fact.
- **Grounded function-calling chat** — the model answers free-form questions using three tools (`lookup_transfer_rates`, `calculate_redemption_value`, `check_expiry`) and may only quote numbers a tool actually returned.
- **Community-extensible dataset** — add a card by editing `data/transfer_rates.yaml`; no code change needed. Rates carry an `as_of` date.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: vanilla + Google Gen AI SDK function calling (no heavyweight agent framework)
- **Models**: Gemini 3.5 Flash (default; override with `MODEL_NAME`)
- **External APIs / Tools**: Google AI Studio (Gemini) — free tier is sufficient

---

## Architecture & Data Flow

```
portfolio.yaml ─┐
                ├─▶ portfolio.py ─▶ engine.py ──────────────▶ main.py ─▶ terminal
transfer_rates ─┘   (load/validate)  (ALL numbers)            ▲
                                      agent.py ───────────────┘
                                      (Gemini: goal parsing, numbers-free
                                       narration, grounded function-calling chat)
```

The LLM only plans and explains. It receives a portfolio summary and tool results; it never invents figures. `optimize` narration is checked to contain no digits (the table is the source of truth); chat answers are checked against the exact numbers its tools returned.

---

## Prerequisites

- Python 3.10+
- `pip`
- A Gemini API key (free, from https://aistudio.google.com/apikey) — only for `optimize --goal` and `chat`. `expiry` and `optimize --category` need no key.

---

## Installation & Setup

```bash
cd agents/card-rewards-optimizer
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
```

**Provide your Gemini key** (only for `optimize --goal` and `chat`). Recommended: export it as an environment variable so it never touches disk —

```bash
export GEMINI_API_KEY="your-key-here"
```

The key lives only in that shell session. `.env.example` lists the variables the project reads; if you prefer, `cp .env.example .env` and put the key there instead (`.env` is gitignored and never committed). Either way, the key is read from the environment at runtime.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | For `optimize --goal` and `chat` only | *None* | Google AI Studio key. Not needed for `expiry` / `optimize --category`. |
| `MODEL_NAME` | No | `gemini-3.5-flash` | Gemini model identifier. |

Edit your cards and balances in `portfolio.yaml` (copy from `examples/portfolio.yaml`). `card_id` values must match ids in `data/transfer_rates.yaml`.

---

## How to Run

```bash
# Points expiring soon, with the best use of each (no key needed):
python main.py expiry

# Rank redemption routes for a category (no key needed):
python main.py optimize --category flights

# Interpret a free-text goal and narrate a recommendation (needs key):
python main.py optimize --goal "flight to Singapore"

# Interactive grounded Q&A (needs key):
python main.py chat

# Use your own portfolio file:
python main.py optimize --category cash --portfolio portfolio.yaml
```

---

## Example Input & Output

### `expiry` (genuine run, no key)
```
$ python main.py expiry
[!] HDFC Infinia: 20,000 points expire on 2026-11-30 (37 days left)
    best use: smartbuy-flights at 1.00 INR/pt ~ INR 20,000.00
[!] American Express Membership Rewards: 12,000 points expire on 2027-01-15 (83 days left)
    best use: Marriott Bonvoy at 0.45 INR/pt ~ INR 5,400.00

Rates as of 2026-10-24. Indicative valuations for educational purposes — not financial advice.
```

### `optimize --category flights` (genuine run, no key)
```
$ python main.py optimize --category flights
Card                                Route                          INR/pt   Points    Value INR
-----------------------------------------------------------------------------------------------
HDFC Infinia                        smartbuy-flights                 1.00   82,000    82,000.00
Axis Magnus                         edge-travel                      0.80   45,000    36,000.00
HDFC Infinia                        Singapore Airlines KrisFlyer     0.75   82,000    61,500.00
Axis Magnus                         Singapore Airlines KrisFlyer     0.60   45,000    27,000.00

Rates as of 2026-10-24. Indicative valuations for educational purposes — not financial advice.
```

### `optimize --goal "flight to Singapore"` (genuine run, gemini-3.5-flash)
Note the narration contains no numbers — the table below it is the single source of truth.
```
$ python main.py optimize --goal "flight to Singapore"
For your upcoming flight to Singapore, booking through HDFC Infinia via the SmartBuy
flights portal stands out as the absolute best redemption route. This option delivers
the strongest value, allowing your accumulated points to stretch the furthest toward
your airfare. The Axis Magnus card paired with the Edge Travel platform serves as a
strong runner-up, providing a reliable secondary choice for securing your journey.
Ultimately, the Infinia pathway is clearly ahead due to its superior reward yield and
streamlined booking process.

Card                                Route                          INR/pt   Points    Value INR
-----------------------------------------------------------------------------------------------
HDFC Infinia                        smartbuy-flights                 1.00   82,000    82,000.00
Axis Magnus                         edge-travel                      0.80   45,000    36,000.00
HDFC Infinia                        Singapore Airlines KrisFlyer     0.75   82,000    61,500.00
Axis Magnus                         Singapore Airlines KrisFlyer     0.60   45,000    27,000.00

Rates as of 2026-10-24. Indicative valuations for educational purposes — not financial advice.
```

### `chat` (needs key)
Start `python main.py chat` and ask free-form questions, e.g. *"What are my HDFC Infinia points worth on KrisFlyer?"*. The agent answers using its tools and may only quote figures those tools return; if a question falls outside the dataset it says so rather than guessing.

---

## How to Test

```bash
# Offline suite (no key, no network) — 28 tests:
pytest

# Live golden-set evals (needs key) — measures goal parsing + tool selection.
# Makes ~13 model calls; on the Gemini free tier (5 requests/min, 20/day) a single
# run fits a day's budget. Throttle with --sleep if you hit per-minute limits:
python evals/run_evals.py
```
<!-- CAPTURE: paste the eval result line, e.g. "12/13 passed on gemini-3.5-flash, 2026-10-24". -->

---

## Known Limitations

- Transfer rates are **indicative** and compiled from public issuer pages / community guides as of the `as_of` date; they drift. Verify with your issuer before transferring. PRs to `data/transfer_rates.yaml` welcome.
- No live bank data — by design. You declare your cards and balances in `portfolio.yaml`.
- Expiry tracking depends on the batch dates you enter.
- Free-tier Gemini rate limits can slow `chat` / evals; the client retries once on transient errors.
- Tested on macOS and Linux; Windows untested.

---

## Security & Privacy Considerations

- **Secrets**: the key is read from the `GEMINI_API_KEY` environment variable at runtime; never hardcoded. Exporting it (recommended) keeps it off disk entirely; the optional `.env` file is gitignored and never committed.
- **Data privacy**: your portfolio summary and tool results are sent to the Gemini API only during `optimize --goal` and `chat`, and are never stored or logged anywhere. `expiry` and `optimize --category` make no network calls.
- **Safety**: the agent executes no shell commands or arbitrary code; its tools are read-only lookups over the bundled dataset.

---

## Future Improvements

- [ ] Credit-card statement import (PDF/CSV) to populate the portfolio.
- [ ] More cards and transfer partners in the dataset.
- [ ] Devaluation alerts when a partner's rate changes.

---

## License

This project is contributed under the repository's MIT license.
