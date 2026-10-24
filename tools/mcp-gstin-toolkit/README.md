# mcp-gstin-toolkit

> LLMs can't reliably compute a GSTIN check digit or audit a 10,000-row feed by eye. This MCP server gives any AI assistant exact tools for it, so the model handles the reasoning and the email, and the code handles the maths.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Ask an AI assistant "is this GSTIN valid?" and it will usually answer confidently, but checking the 15th character needs a mod-36 checksum that models get wrong. Ask it to audit a GST feed and it writes a new throwaway pandas script every time, with different results each run. Real feeds from travel, hotel and finance systems are full of exactly these problems: mistyped GSTINs, state columns that default to one value, and "UAE" next to "United Arab Emirates".
- **Approach**: Split the work. Exact, tested checks run as MCP tools; the model decides what to check, explains the results and drafts the follow-up. A built-in MCP prompt (`review_gst_feed`) packages the whole workflow: audit → summary → email to the data owner.
- **Intended Users**: Developers and data/ops analysts working with Indian GST data who use an MCP-capable assistant (Gemini CLI, Claude, VS Code, Cursor, etc.), and anyone building agents that need GSTIN checks as a tool. A CLI is included for use without an assistant.

### Key Features
- **`review_gst_feed` prompt**: one-click workflow in MCP clients that support prompts. The model audits the file, writes an annotated copy, summarises the fixes in plain language and drafts an email to whoever owns the feed.
- **GSTIN validation**: format, state code, embedded PAN and PAN holder type, and the official mod-36 check digit, with the *expected* digit returned so typos are easy to fix.
- **CSV audit**: validates every GSTIN in a file, flags rows where the state column disagrees with the GSTIN's registered state, and lists state/country values spelled more than one way. Columns are auto-detected.
- **Annotated output**: optionally writes the CSV back out with `audit_status` (`issue` / `warning` / `ok`) and `audit_issues` columns, including per-row spelling fixes such as `'KA' -> 'Karnataka'`.
- **State lookup**: resolves codes, names and abbreviations (`29`, `KA`, `Karnataka`, `Orissa` → Odisha).
- **No API keys, no network**: everything runs locally and deterministically.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: Model Context Protocol (MCP) Python SDK 2.x (`MCPServer`, stdio transport)
- **Models**: Brought by your MCP client (e.g. Gemini in Gemini CLI, Claude in Claude Code). The server itself calls no model and needs no API key.
- **External APIs / Tools**: None. Standard-library `csv` only.

---

## Architecture & Data Flow

```
[You, in Gemini CLI / Claude / IDE] -- "audit ~/feeds/hotels.csv" --> [LLM]
                                                                       |
                                                    MCP tool call (stdio)
                                                                       v
                                            [gstin-mcp server]
                                             ├── validate_gstin / validate_gstins
                                             ├── lookup_state
                                             └── audit_csv ──> reads local CSV,
                                                               optional annotated CSV out
                                                                       |
[LLM explains the findings] <------------- structured JSON report -----+
```

The model decides *what* to check and explains the result; the server does the exact checks.

| Tool | Purpose |
| :--- | :--- |
| `validate_gstin(gstin_number)` | Validate one GSTIN and break it into state, PAN, holder type, check digit |
| `validate_gstins(gstin_numbers)` | Validate a list; counts valid/invalid/repeated |
| `lookup_state(code_or_name)` | Convert between GST state code and state name |
| `audit_csv(path, gstin_column?, state_column?, country_column?, output_path?, max_issues?)` | Audit a CSV feed and optionally write an annotated copy |

| Prompt | Purpose |
| :--- | :--- |
| `review_gst_feed(path, recipient?)` | Audit → plain-language summary → draft email to `recipient` (default "the data team") |

---

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- An MCP client if you want to use it from an assistant (e.g. [Gemini CLI](https://github.com/google-gemini/gemini-cli), Claude Code / Claude Desktop, VS Code)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/mcp-gstin-toolkit
   ```

2. **Create a virtual environment and install:**
   ```bash
   uv venv
   uv pip install -e '.[dev]'
   ```
   Or with pip:
   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -e '.[dev]'
   ```

3. **Environment variables:** none needed. `.env.example` is included only to follow the repository template.

### Connect it to an MCP client

Replace `/absolute/path/to` with where you cloned the repo.

**Gemini CLI** (`~/.gemini/settings.json`):
```json
{
  "mcpServers": {
    "gstin-toolkit": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/tools/mcp-gstin-toolkit", "run", "gstin-mcp"]
    }
  }
}
```

**Claude Code:**
```bash
claude mcp add gstin-toolkit -- uv --directory /absolute/path/to/tools/mcp-gstin-toolkit run gstin-mcp
```

**Claude Desktop / VS Code / Cursor:** use the same `command` + `args` as the Gemini CLI entry in that client's MCP config.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| *(none)* | — | — | The server needs no configuration or secrets. |

---

## How to Run

```bash
# As an MCP server over stdio (normally your MCP client starts this for you)
uv run gstin-mcp

# As a CLI, no MCP client needed
uv run gstin-toolkit validate 27AAPFU0939F1ZV 29AAACZ0001A1Z4
uv run gstin-toolkit audit examples/sample_feed.csv
uv run gstin-toolkit audit examples/sample_feed.csv --output audited.csv
```

---

## Example Input & Output

All data in `examples/sample_feed.csv` is **synthetic**: made-up supplier names and GSTINs generated with valid check digits, plus deliberate errors.

### Example 1: a mistyped GSTIN
```bash
uv run gstin-toolkit validate 27AAPFU0939F1ZX
```
```json
{
  "gstin": "27AAPFU0939F1ZX",
  "valid": false,
  "errors": ["check digit is 'X', expected 'V' (likely a typo)"],
  "state_code": "27",
  "state": "Maharashtra",
  "pan": "AAPFU0939F",
  "pan_holder_type": "Firm / LLP",
  "expected_check_digit": "V"
}
```

### Example 2: auditing a feed
Prompt in an MCP client: *"Audit examples/sample_feed.csv and tell me what needs fixing."*
The model calls `audit_csv`, which returns (trimmed):
```json
{
  "rows": 15,
  "summary": {
    "rows_with_issues": 7,
    "rows_with_warnings_only": 5,
    "invalid_gstin": 1,
    "missing_gstin": 1,
    "state_mismatch": 5,
    "unknown_state_value": 0,
    "nonstandard_spelling": 5
  },
  "issues": [
    {"line": 3,  "issue": "nonstandard_spelling", "detail": "state 'KA' -> 'Karnataka'"},
    {"line": 4,  "gstin": "33AAFCZ0002B1Z7", "issue": "state_mismatch",
     "detail": "state column says Uttar Pradesh but GSTIN is registered in Tamil Nadu"},
    {"line": 6,  "gstin": "27AAACZ0003C1Z0", "issue": "invalid_gstin",
     "detail": "check digit is '0', expected '2' (likely a typo)"},
    {"line": 7,  "issue": "nonstandard_spelling", "detail": "country 'INDIA' -> 'India'"},
    {"line": 8,  "issue": "nonstandard_spelling", "detail": "state 'Orissa' -> 'Odisha'"},
    {"line": 9,  "gstin": "", "issue": "missing_gstin", "detail": "GSTIN is empty"},
    {"line": 10, "issue": "nonstandard_spelling", "detail": "country 'UAE' -> 'United Arab Emirates'"},
    {"line": 11, "issue": "nonstandard_spelling", "detail": "state 'New Delhi' -> 'Delhi'"},
    {"line": 13, "gstin": "36AAACZ0006F1ZU", "issue": "state_mismatch",
     "detail": "state column says Uttar Pradesh but GSTIN is registered in Telangana"},
    {"line": 14, "issue": "state_mismatch", "detail": "... registered in Kerala"},
    {"line": 15, "issue": "state_mismatch", "detail": "... registered in Rajasthan"},
    {"line": 16, "issue": "state_mismatch", "detail": "... registered in West Bengal"}
  ],
  "most_common_states": [["Uttar Pradesh", 5], ["Maharashtra", 2], ["Delhi", 2], ...],
  "inconsistent_spellings": {
    "state":   [{"canonical": "29", "variants": {"Karnataka": 1, "KA": 1}},
                {"canonical": "07", "variants": {"Delhi": 2, "New Delhi": 1}}],
    "country": [{"canonical": "IN", "variants": {"India": 12, "INDIA": 1}},
                {"canonical": "AE", "variants": {"UAE": 1, "United Arab Emirates": 1}}]
  }
}
```
"Uttar Pradesh" is the most common state in the feed (5 of 15 rows), yet every one of those GSTINs is registered somewhere else. That pattern usually means the source system fills in a default state; `most_common_states` together with the mismatches makes it easy to spot.

With `output_path` set, each row gets `audit_status` = `issue` (a GSTIN or state error), `warning` (only a spelling to standardise) or `ok`, and `audit_issues` describes what to change. States are standardised to the official GST name; countries to the most common (then longest) spelling already used in the feed.

### Example 3: a real assistant session
Recorded in Claude Code (desktop, macOS) on 24 Oct 2026 with this server connected. Responses are trimmed but not reworded. This run used an earlier, 12-row version of the sample, where the state column was named `place_of_supply_state`.

> **User:** Validate GSTIN 27AAPFU0939F1ZX
>
> *→ calls `validate_gstin`*
>
> **Assistant:** **Not valid: the last character (the check digit) is wrong.** The last character is `X`, but it should be `V` (probably a typo). Corrected GSTIN: `27AAPFU0939F1ZV`. State 27 – Maharashtra, PAN AAPFU0939F, Firm / LLP. … This tool only checks the format and math, so it can't tell whether `27AAPFU0939F1ZV` is actually registered.

> **User:** Audit tools/mcp-gstin-toolkit/examples/sample_feed.csv and tell me what to fix
>
> *→ calls `audit_csv`*
>
> **Assistant:** 4 of its 12 rows have issues … Line 6: the last character (check digit) should be `2`, not `0`. Probably `27AAACZ0003C1Z2`; confirm with the supplier. … **Note on lines 4 and 13:** the audit compared the GSTIN against the `place_of_supply_state` column. For a sale between two states, the place of supply is supposed to differ from the supplier's state. Those two rows may be correct …

> **User:** Write an annotated copy to /tmp/audited.csv
>
> *→ calls `audit_csv` with `output_path`*
>
> **Assistant:** I wrote the annotated copy to `/tmp/audited.csv` and checked it: it has the header plus all 12 rows, with two new columns …

The second answer shows the split working: the tool supplied exact facts, and the model added judgement the tool can't (place of supply vs supplier state). That feedback led to the `supplier_state` column in the current sample and to per-row spelling warnings.

---

## How to Test

```bash
uv run pytest
```
Expected: `14 passed`. The tests cover the check-digit algorithm against a widely published sample GSTIN, format errors, state aliases, the full audit of the sample feed (including the annotated CSV output), and an end-to-end test that starts the server over stdio and lists/calls its tools and prompt as an MCP client.

Manual MCP check: add the server to your client, then ask it to *"validate 27AAPFU0939F1ZX"*. It should call `validate_gstin` and report the expected check digit `V`. In clients that expose MCP prompts, run `review_gst_feed` with `examples/sample_feed.csv` to try the full audit → summary → email workflow.

### Verification log

| Date | Environment | What was checked | Result |
| :--- | :--- | :--- | :--- |
| 24 Oct 2026 | macOS 27.0.1, Python 3.12, MCP SDK 2.3, `uv` | `pytest` (14 tests, including the stdio client test that lists and fetches `review_gst_feed`) | All passed |
| 24 Oct 2026 | Claude Code desktop (Opus 5.5), server registered in `~/.claude.json` | Tool discovery; `validate_gstin`, `audit_csv` (with and without `output_path`) called by the assistant | Matched expected results (see Example 3) |
| 24 Oct 2026 | Same | `review_gst_feed` run as the slash command `/mcp__gstin-toolkit__review_gst_feed` with the file attached as an @-mention and `Ops` as recipient; the prompt text was fetched from the server | Assistant called `audit_csv`, wrote the annotated copy, reported 4 errors and 5 spelling fixes on the 12-row sample of the time, drafted an email listing only real issues, and included the registration caveat |

Notes from that run:
- In the Claude Code desktop app, attach the file with `@` (pick it from the list); a typed path is rejected by the app before it reaches the server. The file then arrives as `@path`, which the prompt now strips.
- The assistant declined to call Uttar Pradesh a "default value" because, in the 12-row sample, it only tied with two other states. The sample now has 15 rows with Uttar Pradesh clearly dominant, so the pattern the prompt asks about is actually present.

---

## Known Limitations

- Validates **structure and checksum only**. A GSTIN that passes may still be unregistered, cancelled or suspended; checking live status needs the GST portal / a GSP API (not included).
- Non-standard registrations (e.g. some UN bodies, non-resident OIDAR, TDS/TCS GSTINs) may produce warnings even when legitimate.
- State matching assumes the state column means the **supplier's registered state**. If your column is place of supply for an inter-state invoice, mismatches can be legitimate.
- Country normalization covers a short list of common countries; others are only grouped by case and punctuation.
- Tested on macOS with Python 3.12 and MCP SDK 2.3; Windows untested.

---

## Security & Privacy Considerations

- **Secrets Handling**: No credentials are used or stored.
- **Data Privacy**: Everything runs locally. The server makes no network calls; CSV contents only reach your model provider if your MCP client sends the tool results to it (as any MCP client does).
- **Safety**: No shell or code execution. `audit_csv` reads the CSV path you give it and, only if `output_path` is set, writes one CSV file. Run it only from clients you trust with your local files.

---

## Future Improvements

- [ ] Optional live GSTIN status lookup via a GSP/GST API (behind an env-var key).
- [ ] Validate GSTIN against PAN columns and flag the same PAN registered under different names.
- [ ] Support Excel input and very large files (streaming).
- [ ] Prompt template for "draft an email to the data team listing unresolved feed issues".

---

## License

*This project is contributed under the repository's open-source license.*
