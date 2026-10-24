# QuickCart Advisor

> A Go AI agent that compares one product across Swiggy Instamart, Blinkit, Zepto and Amazon India and recommends where to buy — by total delivered cost (fees, memberships, ETA), never the headline price alone, and with strict honesty about where every number came from.

**Phase 1 (current)**: a **bundled offline demo catalog always powers every local run** — zero external calls, deterministic, clearly labeled. **Phase 2 (roadmap)**: real Internet prices via web sources and/or **[MCP](https://modelcontextprotocol.io/) servers**, with qbuys as an optional live adapter. See [Data sources & phases](#data-sources--phases).

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Indian quick-commerce prices are fragmented. The same product differs across Instamart, Blinkit, Zepto and Amazon India not just in sticker price but in delivery fees, platform/handling/small-cart fees, membership benefits (Amazon Prime, Instamart One, Blinkit/Zepto passes) and delivery ETAs — so "where is it cheapest?" is a per-PIN-code arithmetic question no app answers directly.
- **Intended Users**: Shoppers in India deciding which retailer to order a specific product from, and developers looking for a reference ADK-Go agent that keeps all arithmetic in deterministic Go code while the LLM only orchestrates tool calls and formats the answer.

### Key Features
- **Product identification**: resolves a product from a pasted retailer URL (platform + slug hints) or free-text description via the `identify_product` tool.
- **4-retailer comparison**: fetches per-PIN-code offers for Swiggy Instamart, Blinkit, Zepto and Amazon India (`check_serviceability` + `get_offers`), each offer fully itemized — price vs MRP, delivery/platform/handling/small-cart fees, taxes, discounts, ETA, stock and serviceability.
- **Fee- and membership-aware ranking**: `compare_offers` deterministically ranks by final delivered cost, applying memberships such as Amazon Prime, Instamart One, and Blinkit/Zepto passes; it names a best overall, cheapest and fastest with the savings-vs-speed trade-off.
- **Human-in-the-loop purchase approval**: `request_purchase_confirmation` (ADK `RequireConfirmation`) gates any checkout/subscribe/pay step; the agent never places an order itself — it hands you the retailer's own link after approval.

---

## Technical Stack

- **Language & Runtime**: Go 1.26
- **Agent Framework / Core Library**: Google [ADK-Go](https://google.github.io/adk-docs/) `google.golang.org/adk/v2` v2.6.0 (single LLM agent + function tools, in-memory sessions, ADK confirmation flow for HITL)
- **Models**: Pluggable LLM backend —
  - **Default (local)**: any OpenAI-compatible Chat Completions server, e.g. LM Studio at `http://localhost:1235/v1`, model `google/gemma-4-12b` (via ADK-Go `openaimodel` with `APIChatCompletions`)
  - **Alternative**: Google Gemini via the genai client (`gemini-flash-latest` by default), authenticated with `GOOGLE_API_KEY`
- **External APIs / Tools (Phase 1)**: none required — the **offline demo catalog is bundled and always available** for all four retailers. **Optional adapters**: a best-effort open-source **qbuys** ecosystem ([qbserver / qbuys-server](https://github.com/vysakh0/qbuys-server)) client for live Instamart/Blinkit/Zepto data (opt-in; Amazon is never covered by it). **Phase 2 (planned)**: real Internet prices via web sources and/or **MCP servers**. All money in integer paise.

---

## Architecture & Data Flow

A single ADK LLM agent orchestrates five function tools. **All math — fees, totals, discounts, membership benefits, ranking — is done in Go**; the LLM only decides which tool to call and formats the results. The system prompt pins this workflow, in order:

```
Product URL and/or free-text query + 6-digit PIN code
        |
        v
[LLM agent] --1--> identify_product      (resolve product; URL gives platform+slug hints only)
        |          -- found=false? ask a clarifying question, never guess
        |
        +--2--> check_serviceability     (once per retailer: instamart | blinkit | zepto | amazon)
        |
        +--3--> get_offers               (one fan-out call; offers labeled per retailer)
        |          |
        |          +--> Phase 1 (default): offline demo catalog -> all four retailers, no network
        |          +--> Phase 1 (optional): qbuys live source, quick-commerce only (never Amazon)
        |          +--> Phase 2 (planned): real Internet web sources and/or MCP servers
        |
        +--4--> compare_offers           (deterministic Go ranking, membership-aware)
        |
        v
Markdown comparison table + Best overall / Cheapest / Fastest
        |
        +--5--> request_purchase_confirmation   (HITL gate; agent never transacts)
```

Every offer carries a provenance label — `offline-demo-catalog` (bundled static demo data) or `qbuys-live` (fetched at run time from a live adapter) — plus a last-updated timestamp, and the agent must state per retailer which label applies.

### Data sources & phases

| Phase | Retailer data source | Status |
| :--- | :--- | :--- |
| **Phase 1 — offline demo (default)** | **Bundled offline demo catalog serves all four retailers** for every local run: deterministic, zero network, clearly labeled `offline-demo-catalog`, never presented as live prices. Ideal for demos and tests — it always works with no services running. | Current |
| **Phase 1 — optional live adapter** | Open-source **qbuys** ecosystem (Instamart/Blinkit/Zepto only; **Amazon is never covered**). Enable explicitly with `--qbuys-base-url` / `QBUYS_BASE_URL`; offers it returns are labeled `qbuys-live`. If enabled but unreachable, the run falls back to the demo catalog with a warning. | Available |
| **Phase 2 — real Internet / MCP** | Real-time prices fetched from **retailer web sources and/or [MCP](https://modelcontextprotocol.io/) servers** (a retailer-aggregator MCP server, or small per-retailer MCP tools), replacing the demo catalog with live data. | Planned |

---

## Prerequisites

- Go 1.26+ (`go version`)
- One LLM backend:
  - **Local (default)**: [LM Studio](https://lmstudio.ai/) (or any OpenAI-compatible server) loaded with `google/gemma-4-12b`, serving Chat Completions on `http://localhost:1235/v1` — no real API key needed; or
  - **Gemini**: a `GOOGLE_API_KEY` from Google AI Studio.
- *No other services needed for a local demo (Phase 1)*: the offline demo catalog is bundled and always used by default.
- *Optional (Phase 1 live adapter)*: a [qbserver / qbuys-server](https://github.com/vysakh0/qbuys-server) instance, supplied via `QBUYS_BASE_URL`, adds live Instamart/Blinkit/Zepto data on top of the always-on demo catalog.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/quickcart-advisor
   ```

2. **Build:**
   ```bash
   go build ./...
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env   # then edit; or export the variables directly
   ```

---

## Configuration & Environment Variables

Every flag falls back to the corresponding environment variable.

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `LLM_BACKEND` | No | `openai` | `openai` = OpenAI-compatible Chat Completions endpoint (e.g. LM Studio); `gemini` = Google Gemini API. |
| `OPENAI_BASE_URL` | No | `http://localhost:1235/v1` | Base URL of the OpenAI-compatible server (`openai` backend only; LM Studio's default port here is 1235). |
| `OPENAI_MODEL` | No | `google/gemma-4-12b` | Model identifier on the backend. With `--backend gemini` and no `OPENAI_MODEL` set, the default switches to `gemini-flash-latest`. |
| `OPENAI_API_KEY` | No | `local` | API key for the Chat Completions server; any non-empty placeholder works for local servers. |
| `GOOGLE_API_KEY` | Yes, for `gemini` backend | *None* | Google AI Studio API key. Pass via env or `--api-key` (`gemini.NewModel` also reads `GOOGLE_API_KEY` itself when the flag/env is empty). |
| `MODEL_NAME` | No | — | Unused alias — set `OPENAI_MODEL` instead; the Gemini default is `gemini-flash-latest`. |
| `QBUYS_BASE_URL` | No | *(empty)* | Base URL of the optional qbuys live-offers adapter (e.g. `http://localhost:8080`). Empty/unset = demo catalog only. When set but unreachable, the run falls back to the demo catalog with a warning. |
| `OFFLINE_DEMO` | No | `true` | When `true` (default), force the bundled offline demo catalog for **all four retailers** and skip live adapters — recommended for local demos. Set `false` and provide `QBUYS_BASE_URL` to enable live qbuys data. |

*(Never commit a real key; `.env` is gitignored.)*

---

## How to Run

**Local LM Studio backend (default), offline demo catalog (always-on for demos):**

```bash
go run ./cmd/quickcart --query "Amul Taaza milk" --pincode 560001
# every offer is labeled "offline-demo-catalog" — no external services needed
```

**Opt into live qbuys data (Phase 1 live adapter):**

```bash
go run ./cmd/quickcart --query "Amul Taaza milk" --pincode 560001 \
  --offline-demo=false --qbuys-base-url http://localhost:8080
```

**Gemini backend:**

```bash
GOOGLE_API_KEY=your_key go run ./cmd/quickcart \
  --backend gemini --query "Amul Taaza milk" --pincode 560001
```

**With a product URL instead of free text:**

```bash
go run ./cmd/quickcart \
  --url "https://www.zeptonow.com/prn/amul-taaza-toned-milk-1-l/prid/xyz" \
  --pincode 560001
```

**Interactive REPL** (no `--compare` / product flags; one comparison per line, empty line to exit):

```bash
go run ./cmd/quickcart
```

Useful flags: `--compare` forces one-shot mode; `--backend`, `--model`, `--base-url`, `--api-key`, `--qbuys-base-url` override the env vars above per run.

---

## Example Input & Output

### Example Input
```
go run ./cmd/quickcart --query "Amul Taaza milk 1L" --pincode 560001
```

### Example Output (illustrative shape — prices, fees, ETAs and data-source labels vary by run and PIN code)
```
QuickCart Advisor — backend=openai model=google/gemma-4-12b base-url=http://localhost:1235/v1 qbuys=http://localhost:8080
All offers are labeled by data source: "qbuys-live" = live qbuys service; "offline-demo-catalog" = bundled demo data (never live prices).

| Retailer | Product | Price | Fees | Final delivered cost | ETA | Source |
| ... | ... | ~~₹70~~ ₹66 | ₹30 delivery + ₹6 handling | **₹102** | 12 min | qbuys-live |

## Swiggy Instamart
- Amul Taaza Toned Milk 1L — ₹66 (MRP ~~₹70~~), delivery ₹30, handling ₹6,
  **final ₹102**, ETA 12 min, in stock, serviceable.
- Data source: qbuys-live (fetched 2026-10-24T09:30:00Z)
- https://www.swiggy.com/instamart/...

...

Data sources: Instamart/Blinkit/Zepto — qbuys-live; Amazon India — offline-demo-catalog
(demo values, may differ from the app; never presented as live prices).

Best overall: Zepto — lowest final delivered cost (₹99).
Cheapest: Zepto at ₹99. Fastest: Blinkit at 8 min.
Amazon saves ₹5 but takes up to 3 days to a remote PIN; Zepto delivers in 11 minutes for ₹5 more.

(No order is placed. If you ask to check out, the agent asks your approval via
request_purchase_confirmation, then hands you the retailer's own link.)
```

---

## How to Test

```bash
cd agents/quickcart-advisor
go test ./...        # unit + tool-handler tests; no LLM or live server needed
```

The tests cover the deterministic Go side: ranking/fee math and the offline catalog source (`internal/retailers`), and the tool handlers including provenance labels and the live-qbuys-failure fallback (`tools/`, exercising `internal/tools` against an unreachable qbuys URL). `internal/qbuys` and `internal/agent` currently have no test files.

Manual smoke check (offline demo path, works with no LM Studio model loaded errors aside): run the one-shot command above against a running LM Studio server and verify the reply states a `qbuys-live` or `offline-demo-catalog` source per retailer and ends with winner explanations.

---

## Known Limitations

- The **offline demo catalog is the always-on default (Phase 1)**: bundled, static, clearly labeled `offline-demo-catalog` demo data for all four retailers — it always powers local demos and tests, and is *never* presented as live prices. Live adapter/qbuys data is opt-in only.
- **Amazon is not covered by any live source**; Amazon India offers always come from the offline demo catalog.
- **qbuys live data is optional and off by default** (no real-time public APIs exist for Instamart/Blinkit/Zepto). Even when enabled via `QBUYS_BASE_URL`, the best-effort open-source [qbserver / qbuys-server](https://github.com/vysakh0/qbuys-server) **may be unreachable, deactivated, rate-limited or down** — any failure falls back to the demo catalog.
- Product identification is also resolved against the offline catalog (deterministic, not live); live retailer page scraping is intentionally out of the Phase 1 scope (Phase 2: real Internet / MCP).
- Single in-memory sessions per run; no conversation memory across process restarts.

---

## Security & Privacy Considerations

- **Secrets Handling**: credentials come from environment variables / flags only; `.env` is gitignored and `.env.example` contains placeholders, no real secrets. Local LM Studio needs no real key.
- **Data Privacy**: prompts (your product query and PIN code) are sent to the configured LLM backend — keep that in mind when using the hosted Gemini backend versus a fully local LM Studio setup. Live offer lookups go only to your `QBUYS_BASE_URL`.
- **Safety**: the agent executes no shell commands and **never** places orders, subscribes, or pays — the only "action" is `request_purchase_confirmation`, an ADK human-in-the-loop approval gate that ends with the user completing the purchase in the retailer's own app or site.

---

## Future Improvements (Phase 2)

- [ ] **Real Internet data**: fetch live prices from retailer web sources, replacing the demo catalog.
- [ ] **MCP servers**: expose the comparison as a [Model Context Protocol](https://modelcontextprotocol.io/) server, and/or consume retailer-aggregator / per-retailer MCP servers for live Instamart/Blinkit/Zepto/Amazon data.
- [ ] Caching of live responses per (product, pincode) with TTLs.
- [ ] Richer product identification (moderated scraping or catalog search APIs) beyond the demo catalog.
- [ ] Persistent sessions / history-aware follow-ups ("same as yesterday, but to 400007").

---

## License

*This project is contributed under the repository's open-source license.*
