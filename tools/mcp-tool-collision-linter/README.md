# MCP Tool Collision Linter

> Find MCP tools from different servers that a model will mix up, measure how often it actually does, and get description rewrites that fix it.

**Category:** Evaluation, Testing & Safety Utilities
**Stack:** TypeScript · Node.js 20+ · Model Context Protocol SDK · Anthropic / OpenAI / any OpenAI-compatible endpoint (Ollama, vLLM, LM Studio)

---

## The problem

Every MCP server is written on its own, and each one describes its tools well *in isolation*. Problems appear once an agent loads several servers at once. A notes server ships `search_notes`, a drive server ships `search_files`, and both say "search by keyword, return matching titles and snippets". From the model's side these are near-duplicates. It picks one, often the wrong one, and nothing errors. The agent simply answers from the wrong data.

Existing inspectors look at one server at a time, so this cross-server interference goes unmeasured. This linter measures it.

## How it works

```
 MCP config ──► 1. Collect ──► 2. Static scan ──► 3. Probe ──► 4. Score ──► 5. Rewrite ──► 6. Re-test
 or snapshot      tools/list     TF-IDF + names    realistic     swapped,     disambiguated   before/after
                  from every     + params, rank    prompts with  correct,     descriptions    confusion
                  server         look-alike pairs  known answer  other                        rates
```

1. **Collect.** Starts each server in a standard `mcpServers` config (stdio or Streamable HTTP), calls `tools/list`, and shuts it down. You can also pass a JSON snapshot instead.
2. **Static scan.** Scores every cross-server pair on description similarity (TF-IDF with synonym folding, so *find* ≈ *search* and *note* ≈ *document*), name overlap and parameter overlap. This step needs no model and costs nothing.
3. **Probe.** For the most similar pairs, a model writes realistic user requests that each have one clearly correct tool but wording that overlaps the other. You can supply your own hand-labelled probes instead.
4. **Score.** Each probe is sent to the model with the **full tool list** loaded, as a real agent would see it, and the tool it picks is recorded. Per pair, the linter reports:
   - **Swapped**: the share of probes that went to the other tool in the pair.
   - **Correct**: the share that went to the intended tool.
   - **Other**: the share that went to a third tool or no tool.
5. **Rewrite.** For pairs with swaps, the model drafts new descriptions for both tools. Each draft keeps the tool truthful and adds a "Use when / Not for" boundary based on data source or scope. Drafts never name the other server, since the servers don't know about each other.
6. **Re-test** (`--verify-rewrites`). Re-runs the same probes with the new descriptions and reports confusion before and after, so you can see whether a fix actually works.

## Prerequisites

- Node.js 20 or later
- One of the following:
  - an Anthropic API key
  - an OpenAI API key
  - a local OpenAI-compatible server such as Ollama
  - nothing, if you only use `--static` or `--provider offline`

## Setup

```bash
cd tools/mcp-tool-collision-linter
npm install
npm run build
cp .env.example .env   # then add a key, or skip this step for offline mode
```

Load the env file however you prefer, for example `set -a; source .env; set +a`. The CLI reads ordinary environment variables and never reads `.env` itself.

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Enables the `anthropic` provider (auto-selected when set) |
| `ANTHROPIC_MODEL` | Model id, default `claude-haiku-5-5` |
| `OPENAI_API_KEY` | Enables the `openai` provider |
| `OPENAI_BASE_URL` | Any OpenAI-compatible endpoint, e.g. `http://localhost:11434/v1` for Ollama |
| `OPENAI_MODEL` | Model id, default `gpt-4.1-mini` |

## Usage

Run it against the MCP config you already use. Claude Desktop, Cursor and VS Code all use the same `mcpServers` shape. `${VAR}` references in `env`, `args`, `url` and `headers` are expanded from your environment, so secrets stay out of the file.

```bash
node dist/cli.js --config ~/path/to/mcp-config.json
```

Common variations:

```bash
# Free first pass: which pairs look alike? No model calls.
node dist/cli.js --config mcp.json --static

# Measure, rewrite, and prove the rewrite helps
node dist/cli.js --config mcp.json --verify-rewrites

# Local model through Ollama
OPENAI_BASE_URL=http://localhost:11434/v1 OPENAI_MODEL=qwen3:8b node dist/cli.js --config mcp.json --provider openai

# Your own labelled test set instead of generated probes
node dist/cli.js --config mcp.json --probes my-probes.json

# Snapshot live servers once, then lint the snapshot anywhere (CI, offline)
node dist/cli.js --config mcp.json --static --dump-tools tools.snapshot.json
node dist/cli.js --tools tools.snapshot.json

# Markdown report for a PR comment
node dist/cli.js --tools tools.snapshot.json --format markdown --out collisions.md
```

Run `node dist/cli.js --help` for all flags. The most useful ones are:

| Flag | Default | What it does |
|---|---|---|
| `--max-pairs` | 10 | How many of the most similar pairs to probe; this caps cost |
| `--probes-per-tool` | 4 | Generated prompts per tool per pair |
| `--context` | `all` | `all` shows the model every loaded tool (realistic); `pair` shows only the two, isolating the pair |
| `--threshold` | 0.3 | Minimum static similarity for a pair to count as look-alike |
| `--fail-on` | off | Exit 1 if any pair reaches `low`, `medium` or `high` severity |

**Cost:** a run makes about `max-pairs × (1 + 2 × probes-per-tool)` model calls, plus one call per rewrite, and twice the probe calls with `--verify-rewrites`. Defaults are around 90 short calls.

### Hand-written probes

A list of prompts, each with the tool that should handle it. You can reference a tool as `server/tool`, `server__tool`, or a bare name if it is unique.

```json
[
  { "prompt": "Find the note where I jotted down the wifi password", "intended": "notes/search_notes" },
  { "prompt": "Pull up the project proposal PDF Priya sent over",   "intended": "drive/search_files" }
]
```

Hand-labelled probes are the most trustworthy test set, because a person decided the right answer. Where they cover a pair, they replace generated probes for that pair.

### Severity

| Severity | Rule |
|---|---|
| high | ≥ 25% of probes swapped between the two tools |
| medium | ≥ 10% swapped |
| low | any swaps, or under 75% correct overall (probes leaking to a third tool) |
| none | no swaps and ≥ 75% correct |

## Try it without any servers or keys

`examples/` contains five small servers with deliberately overlapping tools (`notes`, `drive`, `chat`, `mail` and `calendar`), served by a tiny stdio MCP server, plus a labelled probe set.

```bash
npm run demo        # lint the snapshot with the offline router
npm run demo:live   # start the five example servers over stdio and lint them
```

Here is real output from `npm run demo` with `--max-pairs 4`:

```
MCP tool collision report
11 tools from 5 servers (notes, drive, chat, mail, calendar) · 9 look-alike pairs · provider: offline (lexical router)

SEVERITY  SWAPPED  CORRECT  OTHER  STATIC  PAIR
HIGH      50%      50%      0%     0.91    notes/search_notes  ↔  drive/search_files
NONE      0%       100%     0%     0.89    notes/create_note  ↔  drive/create_document
NONE      0%       100%     0%     0.81    chat/send_message  ↔  mail/send_email
NONE      0%       100%     0%     0.55    chat/search_messages  ↔  mail/search_inbox
SWAPPED: sent to the other tool in the pair · OTHER: sent to a third tool or none

notes/search_notes  ↔  drive/search_files
  4/4 meant for search_notes went to drive/search_files; 0/4 meant for search_files went to notes/search_notes
  overlapping terms: search, document, keyword, snippet, result, match, person, title
  ✗ "Can you search my notes by keyword and return matching notes with titles and snippets?"
      wanted notes__search_notes, got drive__search_files
  ...
```

With a real model, each high or medium pair also shows suggested descriptions. With `--verify-rewrites`, it adds a line such as `Re-tested: confusion 50% → 0%, correct 50% → 100%`.

**About offline mode:** it replaces the model with a lexical router and uses template probes. This is good enough to see the pipeline work, run CI without secrets, and catch obvious overlaps. Its numbers are not model behaviour, though; real measurement needs a model.

## Use in CI

```yaml
- run: npm ci && npm run build
  working-directory: tools/mcp-tool-collision-linter
- run: node dist/cli.js --tools ../../mcp-tools.snapshot.json --fail-on high --format markdown --out collisions.md
  working-directory: tools/mcp-tool-collision-linter
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

Exit codes: `0` means OK, `1` means a pair reached the `--fail-on` severity, and `2` means a usage or runtime error.

## Programmatic use

```ts
import { loadFromMcpConfig, createProvider, lint, toMarkdown } from "mcp-tool-collision-linter";

const tools = await loadFromMcpConfig("mcp.json");
const report = await lint(tools, createProvider("anthropic"), { maxPairs: 5, verifyRewrites: true });
console.log(toMarkdown(report));
```

## Project structure

```
mcp-tool-collision-linter/
├── src/
│   ├── cli.ts          # Flags, I/O, exit codes
│   ├── index.ts        # lint() and public exports
│   ├── collect.ts      # Start servers from an mcpServers config / load snapshots; provider-safe ids
│   ├── similarity.ts   # Tokeniser, synonym folding, TF-IDF, pair scoring
│   ├── probes.ts       # Model-written, template and hand-written probes
│   ├── evaluate.ts     # Routing runs, metrics, severity, rewrites, re-test
│   ├── providers.ts    # Anthropic, OpenAI-compatible, offline router
│   ├── report.ts       # Text, Markdown, JSON
│   └── types.ts
├── examples/
│   ├── colliding-tools.json   # Snapshot of 11 overlapping tools on 5 servers
│   ├── fixture-server.ts      # Tiny stdio MCP server serving one server from the snapshot
│   ├── mcp-config.json        # Starts the five fixture servers
│   └── probes.json            # Hand-labelled probes
└── test/                      # node:test suites (no network, no keys)
```

## Testing

```bash
npm test         # 18 tests: scoring, live stdio servers, mocked Anthropic/OpenAI APIs, full pipeline
npm run typecheck
```

The provider tests run against a local mock HTTP server. The pipeline test uses a scripted model that confuses two tools until their descriptions are rewritten, which exercises the full probe → rewrite → re-test loop without any API key.

## Known limitations

- **Results are model-specific.** A pair that one model confuses, another may not. Lint with the model your agent actually uses.
- **Generated probes inherit the model's view.** If the same model writes and answers the probes, it can miss blind spots it shares with itself. Hand-labelled probes, or a different model for generation, give a stricter test.
- **Small samples are noisy.** Four probes per tool means each probe moves a rate by about 12 points. Raise `--probes-per-tool` before trusting small differences.
- **Only the first tool call is scored.** Agents that call both tools, or ask a clarifying question, are scored only on the first tool they pick.
- **Descriptions are what you can change.** Tool names come from the servers, and many clients prefix them differently. The linter scores the client-style id (`server__tool`) but suggests only description changes.
- **OAuth-protected HTTP servers** need a token passed through `headers`. Interactive OAuth flows are not supported. If a server can't be reached, use `--dump-tools` from a machine where it can, then lint the snapshot.
- **Rewrite suggestions are drafts.** Review them before shipping; they are meant to be checked, not applied blindly.

## Security & privacy

- No credentials are stored. Keys are read from environment variables, and `${VAR}` placeholders keep secrets out of config files.
- Tool names, descriptions and schemas are sent to the model provider you choose. Your tools are **not** called; servers are only asked for `tools/list`. Probe prompts are synthetic or yours.
- Offline and `--static` modes make no network calls beyond starting the servers you configured.

## License

MIT, as part of the [open-source-ai](../../README.md) repository.
