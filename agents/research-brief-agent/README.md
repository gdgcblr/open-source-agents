# Research Brief Agent

> Turns a topic plus grounded sources (bundled fixtures or user-supplied URLs) into a structured, citation-aware research report using the Cursor Agent SDK.

---

## Overview

### Problem Statement & Intended Users

- **Problem**: Ad-hoc “research this topic” prompts produce long, unstructured prose with weak or hallucinated citations. Teams need a repeatable brief format and evidence tied to sources they control.
- **Intended Users**: Hackathon contributors, PMs, students, and developers who want offline-friendly demos without paid search APIs.

### Key Features

- **Structured report layout** via the `structured-report` skill (executive summary, evidence table, risks, next steps).
- **Bundled offline sources** under `bot/sandbox/workspace/sources/` for reproducible demos and evals.
- **Optional URL fetch** (`fetch_source`) for public http(s) pages the user explicitly provides.
- **Smoke eval** asserts tool use and required report headings.

---

## Technical Stack

- **Language & Runtime**: TypeScript on Node.js 22.13+ (Agent SDK requirement; do not use Bun)
- **Agent Framework**: [Cursor Agent SDK](https://cursor.com/docs/bdk) (`@grok/agent-sdk`)
- **Models**: Default `grok-4.5` with high effort (configured in `bot/agent.ts`)
- **External APIs**: Optional outbound HTTP for user-supplied URLs only; no search API keys

---

## Architecture & Data Flow

```
[User topic + optional URLs]
        |
        v
[Agent SDK serve / playground]
        |
        +--> list_bundled_sources / read_bundled_source (fixtures)
        +--> fetch_source (public URLs)
        |
        v
[Model applies structured-report skill]
        |
        v
[Markdown report with ## headings + Sources section]
```

---

## Prerequisites

- Node.js **22.13+**
- npm
- **CURSOR_API_KEY** (or `npx @grok/agent-sdk login`) for model turns — not required for `validate`, `tool call`, or `npm run check`

---

## Installation & Setup

1. **Navigate to the project directory:**

   ```bash
   cd agents/research-brief-agent
   ```

2. **Install dependencies:**

   ```bash
   npm install
   ```

3. **Configure environment (for live runs and evals):**

   ```bash
   cp .env.example .env
   # Set CURSOR_API_KEY in .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `CURSOR_API_KEY` | For model turns | *None* | Cursor API key for `run`, `eval`, and playground |
| `OTEL_*` | No | — | Optional telemetry export (Agent SDK) |

---

## How to Run

Key-free checks:

```bash
npm run check
npx --yes @grok/agent-sdk@0.2.29 validate --dir .
npx --yes @grok/agent-sdk@0.2.29 info --dir . --json
npm run tool:list-sources
npm run tool:read-fixture
```

Live agent (requires Cursor credential):

```bash
npx --yes @grok/agent-sdk@0.2.29 run --dir . --message "Research edge computing in healthcare using bundled source healthcare-edge.md and produce the full structured report."
npx --yes @grok/agent-sdk@0.2.29 serve --dir . --mode single --dev
# Open http://127.0.0.1:3000/playground
```

Evals (official — uses **Cursor** agent harness, not third-party LLM APIs):

```bash
npx --yes @grok/agent-sdk@0.2.29 eval --dir . --list
npx --yes @grok/agent-sdk@0.2.29 eval --dir .
```

Optional generic smoke test (any OpenAI-compatible endpoint — validates report **shape** only; does not run BDK tool-calling evals):

```bash
pip install -r requirements-dev.txt
# Set SMOKE_* vars in your shell (never commit the key):
#   SMOKE_API_KEY=<your-key>
#   SMOKE_BASE_URL=https://integrate.api.nvidia.com/v1  # or any OpenAI-compatible URL
#   SMOKE_MODEL=z-ai/glm-5.3                            # or any model ID
npm run fixture:save      # generates .agent-serve/fixture.json
npm run smoke             # runs scripts/smoke_test.py
```

---

## Example Input & Output

### Example Input

```
Research "edge computing in healthcare" using the bundled file healthcare-edge.md.
Use the structured report format.
```

### Example Output (abbreviated)

```markdown
## Executive Summary
Edge computing in healthcare reduces latency for monitoring workflows and can limit raw data egress, at the cost of operational complexity at each site.

## Key Findings
- Latency-sensitive vitals workflows benefit from in-facility aggregation (Source: healthcare-edge.md).
- ...

## Evidence Table
| Claim | Source | Confidence |
| ... | healthcare-edge.md | high |

## Risks & Uncertainties
...

## Recommended Next Steps
1. Inventory workflows by latency and privacy tier.
...

## Sources
- healthcare-edge.md (bundled)
```

---

## How to Test

```bash
cd agents/research-brief-agent
npm install
npm run check
npx --yes @grok/agent-sdk@0.2.29 validate --dir .
npm run tool:read-fixture
# With CURSOR_API_KEY set:
npx --yes @grok/agent-sdk@0.2.29 eval --dir . --tags smoke
```

---

## Known Limitations

- No autonomous web search; the model only fetches URLs the user provides.
- `fetch_source` caps response size (256 KB) and blocks localhost/private IP targets.
- HTML pages are stripped to plain text; complex layouts may lose structure.
- Official `agent-sdk eval` requires **CURSOR_API_KEY** (smoke-test keys cannot substitute — evals run the real Cursor agent loop with tools).
- Optional `scripts/smoke_test.py` checks markdown shape via any OpenAI-compatible endpoint; configure via `SMOKE_API_KEY`, `SMOKE_BASE_URL`, `SMOKE_MODEL`.
- Tested on Windows 10 and Node 22; Bun is unsupported by the Agent SDK harness.

---

## Security & Privacy Considerations

- **Secrets**: Load `CURSOR_API_KEY` from `.env` locally; never commit `.env`.
- **Data privacy**: User topics and fetched URL content are sent to Cursor model APIs during turns; bundled fixtures stay local until read by tools.
- **Safety**: Tools are read-only (`effect: "read"`). No shell execution or write tools in this agent.

---

## Future Improvements

- [ ] Optional schedule channel for weekly topic digests from a URL list file.
- [ ] Additional bundled fixtures per domain (climate, fintech).
- [ ] Stricter eval assertions on evidence table row count.

---

## License

This project is contributed under the repository's open-source license.
