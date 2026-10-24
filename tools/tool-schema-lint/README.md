# tool-schema-lint

> A zero-dependency linter that catches broken, provider-incompatible, or poorly described LLM tool definitions (MCP, OpenAI, Gemini, Anthropic) before they fail at runtime or quietly degrade your agent.

**Quick start (about 2 minutes, no API keys):**
```bash
git clone https://github.com/gdgcblr/open-source-agents.git
cd open-source-agents/tools/tool-schema-lint

# Runs immediately, no install needed (use python3 on Linux/macOS if python is not found)
python -m tool_schema_lint examples/calendar_mcp_broken.json --target gemini   # finds 7 errors
python -m tool_schema_lint examples/calendar_mcp_fixed.json --target all       # no problems found

# Run the test suite
python -m venv .venv
.venv\Scripts\activate          # Windows; on Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m pytest                # expected: 105 passed
```
Full details: [Installation & Setup](#installation--setup), [How to Run](#how-to-run), [How to Test](#how-to-test).

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Tool definitions are the API contract between an agent and a model, yet nothing checks them until a request fails. A schema that works with one provider is rejected by another: Gemini's `parameters` object rejects keywords such as `$schema` (added automatically by `zod-to-json-schema`) or `oneOf`, OpenAI strict mode rejects any object without `additionalProperties: false`, and tool names with dots work in MCP but are refused by OpenAI and Anthropic. Other mistakes never raise an error at all: a `required` entry with a typo, a `$ref` to a missing definition, or a one-word description that makes the model pick the wrong tool.
- **Intended Users**: Developers building MCP servers, function-calling agents, or multi-provider agent frameworks who want a fast local or CI check of their tool definitions.

### Key Features
- **Four input formats, auto-detected**: MCP `tools/list` results (raw or JSON-RPC wrapped), OpenAI Chat Completions / Responses / legacy `functions`, Gemini `functionDeclarations`, and Anthropic `tools`.
- **Provider compatibility checks**: 33 rules, each citing the document it is based on. Lint one definition against several providers with `--target gemini --target openai-strict ...`.
- **Structural and quality checks**: undefined `required` properties, unresolved `$ref`s, invalid types, empty or duplicate enums, defaults outside the enum, arrays without `items`, missing or placeholder descriptions, duplicate tool names.
- **Token budget**: estimates how much context the definitions consume and can fail CI over a `--max-tokens` budget.
- **CI-friendly**: text, JSON, or GitHub Actions annotation output; exit codes `0` / `1` / `2`; per-rule disabling; no network access and no API keys.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+ (tested on Python 3.11.0, Windows 11)
- **Agent Framework / Core Library**: Vanilla Python, standard library only (`json`, `argparse`, `re`, `dataclasses`)
- **Models**: N/A. This is a static analysis tool; it never calls a model.
- **External APIs / Tools**: None. Tests use `pytest`.

---

## Architecture & Data Flow

```
 JSON file / stdin
        |
        v
 [loader.py]  detect format per tool (MCP / OpenAI / Gemini / Anthropic)
        |      -> normalized ToolDef(name, description, schema, JSON-pointer location)
        v
 [linter.py]  choose targets per tool (requested, or the tool's own format;
        |      tools with "strict": true also get openai-strict)
        |      run every applicable rule from rules/{general,mcp,openai,gemini,anthropic}.py
        |      rules use schema_walk.py: iterative walk, never follows $ref (cycle-safe)
        v
 [report.py]  text | json | github annotations    -->  exit code 0 / 1 / 2
```

Every finding carries a rule ID, a severity (`error`, `warning`, `info`), the tool name, an RFC 6901 JSON pointer into the original input, a message, and a fix hint.

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.10 or newer
- pip (only needed to install `pytest` for the test suite, or to install the `tool-schema-lint` command)
- No API keys or accounts

---

## Installation & Setup

1. **Get the code and navigate to the project directory:**
   ```bash
   git clone https://github.com/gdgcblr/open-source-agents.git
   cd open-source-agents/tools/tool-schema-lint
   ```
   If you already have the repository, just `cd tools/tool-schema-lint` from its root.

2. **Set up the virtual environment / install dependencies:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt   # pytest, for the test suite
   pip install -e .                  # optional: adds the `tool-schema-lint` command
   ```
   The linter itself has no dependencies; `python -m tool_schema_lint` works from this directory without installing anything.

3. **Configure Environment Variables:**
   Not required. `.env.example` is included for template consistency and documents that no variables are used.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| *(none)* | — | — | The tool reads no environment variables. All configuration is passed as command-line options. |

### Command-line options

| Option | Default | Description |
| :--- | :--- | :--- |
| `FILE ...` | — | One or more JSON files. Use `-` to read standard input. |
| `-t, --target` | the format each tool is written in | Provider rules to apply: `mcp`, `openai`, `openai-strict`, `gemini`, `anthropic`, or `all`. Repeatable. |
| `--input-format` | auto | Force how tool objects are read (`mcp`, `openai`, `gemini`, `anthropic`). Only needed for ambiguous input such as a bare list of `{"name", "parameters"}` objects. |
| `-f, --format` | `text` | Output format: `text`, `json`, or `github` (GitHub Actions annotations). |
| `--fail-on` | `error` | Lowest severity that makes the exit code `1`: `error`, `warning`, `info`, or `never`. |
| `--disable RULE` | — | Skip rules by ID, e.g. `--disable G011,A002`. Repeatable. |
| `--max-tokens N` | — | Report `G016` when the estimated size of all definitions exceeds `N` tokens. |
| `--list-rules` | — | Print the rule catalogue with sources and exit. |

**Exit codes:** `0` no findings at or above `--fail-on`; `1` findings at or above `--fail-on`; `2` usage error or unreadable or unrecognized input.

---

## How to Run

```bash
# Lint an MCP tools/list dump with MCP rules (the default for MCP input)
python -m tool_schema_lint examples/calendar_mcp_broken.json

# Check whether the same tools will work with Gemini, OpenAI and Anthropic
python -m tool_schema_lint examples/calendar_mcp_broken.json --target gemini --target openai --target anthropic

# Check against every provider
python -m tool_schema_lint examples/calendar_mcp_fixed.json --target all

# Machine-readable output / GitHub Actions annotations / token budget
python -m tool_schema_lint examples/openai_strict_tools.json --format json
python -m tool_schema_lint examples/openai_strict_tools.json --format github
python -m tool_schema_lint examples/calendar_mcp_fixed.json --max-tokens 500

# Read from stdin
cat examples/openai_strict_tools.json | python -m tool_schema_lint -

# List every rule with the document it is based on
python -m tool_schema_lint --list-rules
```

After `pip install -e .`, `tool-schema-lint` can be used in place of `python -m tool_schema_lint`.

### Getting the tool definitions to lint
- **MCP server**: save the result of a `tools/list` request as JSON. Both the bare result (`{"tools": [...]}`) and the full JSON-RPC response are accepted. For example, the MCP Inspector CLI can print it: `npx @modelcontextprotocol/inspector --cli <server command> --method tools/list > tools.json` (shown for convenience; not exercised by this project's tests).
- **OpenAI / Anthropic / Gemini code**: dump the `tools` list you pass to the SDK, e.g. `json.dump(tools, open("tools.json", "w"))`.

### Use as a library
```python
from tool_schema_lint import Severity, lint, load_tools, read_json

tools = load_tools(read_json("examples/calendar_mcp_broken.json"))
result = lint(tools, targets=["gemini"])
for f in result.findings[:3]:
    print(f.rule_id, f.severity, f.tool, f.path)
print(result.count(Severity.ERROR), "errors")
```
Output:
```
GM003 error weather.get-forecast /result/tools/0/inputSchema/$schema
GM005 error weather.get-forecast /result/tools/0/inputSchema/properties/days/enum
G013 warning weather.get-forecast /result/tools/0/inputSchema/properties/units/default
7 errors
```

### Use it in your agent's test suite
The most practical way to use the linter while building an agent is to make your tool definitions part of your tests: if anyone adds a tool that a target provider would reject, `pytest` fails before the agent ever calls a model.

[`examples/agent_integration/`](examples/agent_integration/) is a working example for a small trip-planner agent:
- [`agent_tools.py`](examples/agent_integration/agent_tools.py) holds the agent's tools (OpenAI Chat format, `strict: true`, written to be valid for Gemini too).
- [`test_agent_tools.py`](examples/agent_integration/test_agent_tools.py) is the test to copy into your own agent:

```python
from agent_tools import TOOLS

from tool_schema_lint import Severity, lint, load_tools

TARGETS = ["openai-strict", "gemini"]  # the providers this agent must work with


def test_tool_definitions_are_valid_for_every_target_provider():
    result = lint(load_tools(TOOLS), targets=TARGETS)
    errors = [f for f in result.findings if f.severity == Severity.ERROR]
    assert not errors, "\n".join(f"{f.rule_id} {f.tool} {f.path}: {f.message}" for f in errors)
```

Run it with `python -m pytest examples/agent_integration` (it is also part of the main `python -m pytest` run). If a teammate renames `search_flights` to `flights.search` and changes `max_stops` to `"type": ["integer", "null"]`, the test fails with:
```
E       AssertionError: O001 flights.search /0/function/name: function name 'flights.search' contains characters other than a-z A-Z 0-9 _ -
E         GM004 flights.search /0/function/parameters/properties/max_stops/type: type ['integer', 'null'] is an array; Gemini's Schema takes one type
```

To install the linter in another project, point pip at this folder, e.g. `pip install "git+https://github.com/gdgcblr/open-source-agents.git#subdirectory=tools/tool-schema-lint"`.

### Use in CI (GitHub Actions)
The `github` format prints workflow commands that GitHub shows as annotations on the run. Example step (illustrative; this repository does not run it):
```yaml
- name: Lint tool definitions
  run: |
    pip install ./tools/tool-schema-lint
    tool-schema-lint my-server-tools.json --target gemini --target openai --format github
```

### Rule catalogue

| ID | Severity | Targets | Checks | Source |
| :--- | :--- | :--- | :--- | :--- |
| G001 | error | all | Tool has a non-empty name | MCP spec 2025-11-25 `Tool` |
| G002 | error | all | Tool names are unique | MCP spec 2025-11-25 `Tool` |
| G003 | warning | all | Tool has a description | Anthropic "Define tools" best practices |
| G004 | warning | all | Description is at least 40 characters | Anthropic "Define tools" best practices |
| G005 | warning | all | Descriptions are not placeholders (`TODO`, ...) or a copy of the name | Anthropic "Define tools" best practices |
| G006 | error | all | Parameter schema exists (MCP/Anthropic) and its root is `type: object` | MCP spec 2025-11-25 `Tool` |
| G007 | error | all | `properties`, `required`, `enum`, `items`, `description` have the right JSON shape | JSON Schema 2020-12 |
| G008 | error | all | Every `required` entry is defined in `properties` | JSON Schema 2020-12 |
| G009 | error | all | `type` values are valid JSON Schema types | JSON Schema 2020-12 |
| G010 | warning | all | Parameters declare a type | JSON Schema 2020-12 |
| G011 | warning | all | Parameters have descriptions | Anthropic "Define tools" best practices |
| G012 | error | all | `enum` is non-empty and has no duplicates | JSON Schema 2020-12 |
| G013 | warning | all | `default` is one of the `enum` values | JSON Schema 2020-12 |
| G014 | warning | all | Arrays define `items` | JSON Schema 2020-12 |
| G015 | error | all | Every `$ref` resolves inside the schema | JSON Schema 2020-12 |
| G016 | error | all | Definitions fit the `--max-tokens` budget (only with that option) | chars / 4 estimate |
| M001 | warning | mcp | Name is 1-128 chars of `A-Z a-z 0-9 _ - .` | MCP spec 2025-11-25 "Tool Names" (SHOULD) |
| M002 | info | mcp | Parameterless tools set `additionalProperties: false` | MCP spec 2025-11-25 `inputSchema` |
| O001 | error | openai | Name matches `^[a-zA-Z0-9_-]{1,64}$` | OpenAI API 400 validation error (see limitations) |
| O002 | info | openai | Fewer than 20 tools offered at once | OpenAI Function calling guide |
| S001 | error | openai-strict | Every object sets `additionalProperties: false` | OpenAI Structured Outputs "Supported schemas" |
| S002 | error | openai-strict | Every property is in `required` | OpenAI Structured Outputs |
| S003 | error | openai-strict | Root schema does not use `anyOf` | OpenAI Structured Outputs |
| S004 | error | openai-strict | No `allOf`, `not`, `if`/`then`/`else`, `dependentRequired`, `dependentSchemas` | OpenAI Structured Outputs |
| S005 | warning | openai-strict | String `format` is one of the supported formats | OpenAI Structured Outputs |
| S006 | error | openai-strict | ≤10 nesting levels, ≤5000 properties, ≤1000 enum values, ≤120,000 schema string chars, large-enum limit | OpenAI Structured Outputs |
| GM001 | error | gemini | Name starts with a letter or `_`; `a-z A-Z 0-9 _ . : -`; max 128 | `google-genai` `FunctionDeclaration` |
| GM002 | error | gemini | Parameter names start with a letter or `_`; `a-z A-Z 0-9 _`; max 64 | `google-genai` `FunctionDeclaration` |
| GM003 | error | gemini | Only keywords that exist on Gemini's `Schema` object | `google-genai` `Schema` |
| GM004 | error | gemini | `type` is a single value (use `nullable` or `anyOf`) | `google-genai` `Schema` |
| GM005 | error | gemini | `enum` values are strings | `google-genai` `Schema` |
| A001 | error | anthropic | Name matches `^[a-zA-Z0-9_-]{1,128}$` | Anthropic "Define tools" |
| A002 | info | anthropic | Description has at least 3 sentences | Anthropic "Define tools" ("aim for at least 3–4 sentences") |

Sources were checked on 2026-10-24: the [MCP tools spec (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/server/tools), [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) and [Function calling](https://developers.openai.com/api/docs/guides/function-calling) guides, [Anthropic "Define tools"](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools), the `Schema` / `FunctionDeclaration` types in [`googleapis/python-genai` `types.py`](https://github.com/googleapis/python-genai/blob/6bd3d4090e1f/google/genai/types.py) at commit `6bd3d40` (2026-10-23), and the [JSON Schema 2020-12](https://json-schema.org/draft/2020-12) specification.

**Portable optional fields:** OpenAI strict mode needs every property in `required`, so optional values are expressed as nullable. `"type": ["string", "null"]` is rejected by Gemini's `Schema` (GM004), but `"anyOf": [{"type": "string"}, {"type": "null"}]` is accepted by both. `examples/calendar_mcp_fixed.json` uses that form and passes every target.

---

## Example Input & Output

### Example Input
`examples/openai_strict_tools.json`: an OpenAI tool with `strict: true` whose schema is not strict-mode compatible.
```json
[
  {
    "type": "function",
    "function": {
      "name": "lookup_order",
      "description": "Look up an order by id and return its status, items, and delivery estimate.",
      "strict": true,
      "parameters": {
        "type": "object",
        "properties": {
          "order_id": { "type": "string", "description": "Order id, e.g. ORD-10293" },
          "include_items": { "type": "boolean", "description": "Whether to include line items" }
        },
        "required": ["order_id"]
      }
    }
  }
]
```

### Example Output
```
$ python -m tool_schema_lint examples/openai_strict_tools.json
examples/openai_strict_tools.json
  lookup_order
    error   S001   /0/function/parameters
            object does not set "additionalProperties": false (required in strict mode)
            hint: Add "additionalProperties": false to this object.
    error   S002   /0/function/parameters/required
            strict mode requires every property in 'required'; missing: include_items
            hint: Make optional fields required but nullable: "anyOf": [{"type": "string"}, {"type": "null"}] works for OpenAI and Gemini; "type": ["string", "null"] works for OpenAI only.
  1 tool, ~88 tokens (estimate), targets: openai, openai-strict

2 errors, 0 warnings, 0 info
```
Exit code: `1`.

### A larger example: one MCP server, four providers
`examples/calendar_mcp_broken.json` is a `tools/list` response from a hypothetical calendar MCP server with the kinds of mistakes found in real servers. With the default MCP rules:
```
$ python -m tool_schema_lint examples/calendar_mcp_broken.json
examples/calendar_mcp_broken.json
  weather.get-forecast
    warning G013   /result/tools/0/inputSchema/properties/units/default
            default 'kelvin' is not one of the enum values
    error   G008   /result/tools/0/inputSchema/required
            'zip' is required but not defined in 'properties'
            hint: Add the property definition or remove it from 'required' (check for typos).
  search_events
    warning G005   /result/tools/1/description
            description only repeats the tool name
            hint: Explain the behaviour instead of restating the name.
    warning G011   /result/tools/1/inputSchema/properties/query
            parameter 'query' has no description
            hint: Explain what the value means, its format, and give an example.
    warning G014   /result/tools/1/inputSchema/properties/tags
            array has no 'items' schema
            hint: Describe the element type; some providers reject arrays without 'items'.
  create_event
    warning G005   /result/tools/2/description
            description looks like a placeholder: "TODO"
            hint: Replace it with a real explanation of the tool.
    error   G015   /result/tools/2/inputSchema/properties/reminder/$ref
            cannot resolve '#/$defs/Reminder': '$defs' does not exist
            hint: Inline the definition or add it under '$defs'.
  list_calendars
    info    M002   /result/tools/3/inputSchema
            tool takes no parameters but accepts any object
            hint: The MCP spec recommends {"type": "object", "additionalProperties": false} for tools without parameters.
  4 tools, ~443 tokens (estimate), targets: mcp

2 errors, 5 warnings, 1 info
```
Adding `--target gemini` reports five more errors that only appear when the same tools are sent to Gemini (excerpt of the real output):
```
    error   GM003  /result/tools/0/inputSchema/$schema
            '$schema' is not a field of Gemini's Schema object
            hint: Remove it; generators such as zod-to-json-schema add it automatically. Alternatively send this schema as 'parametersJsonSchema'.
    error   GM005  /result/tools/0/inputSchema/properties/days/enum
            enum contains non-string values [1, 3, 7]; Gemini's Schema enum is a list of strings
    error   GM002  /result/tools/1/inputSchema/properties
            parameter name 'time-range' is not valid for Gemini
    error   GM003  /result/tools/1/inputSchema/properties/filter/oneOf
            'oneOf' is not a field of Gemini's Schema object
    error   GM004  /result/tools/1/inputSchema/properties/time-range/properties/start/type
            type ['string', 'null'] is an array; Gemini's Schema takes one type
...
7 errors, 5 warnings, 0 info
```
The corrected file passes every target:
```
$ python -m tool_schema_lint examples/calendar_mcp_fixed.json --target all
examples/calendar_mcp_fixed.json
  no problems found
  4 tools, ~729 tokens (estimate), targets: anthropic, gemini, mcp, openai, openai-strict

0 errors, 0 warnings, 0 info
```

### Failure behaviour
```
$ python -m tool_schema_lint missing.json
tool-schema-lint: error: missing.json: file not found
```
Exit code: `2`. Invalid JSON reports the line and column; unrecognized or ambiguous input asks for `--input-format`.

---

## How to Test

```bash
cd tools/tool-schema-lint
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest
```
Expected: `105 passed` (103 in `tests/` plus the 2 in `examples/agent_integration/`).

The suite runs offline with no mocks and covers:
- **Every rule**: a test fails if a registered rule has no bad-input case. Each rule must fire on its bad case, provider rules must stay silent for other targets, and a shared "good" tool must be clean under all five targets.
- **Loader**: all four formats and their variants, JSON-RPC unwrapping, ambiguous input, empty, malformed, non-UTF-8, BOM, oversized, and pathologically nested input.
- **Edge cases**: recursive `$ref: "#"` (terminates), external `$ref`s, the exact nesting-limit boundary, the `strict: true` flag, Gemini `parametersJsonSchema` vs `parameters`, and upper-case Gemini types.
- **CLI end to end**: exit codes, `--fail-on`, `--disable`, `--max-tokens`, text / JSON / GitHub output, multiple files, and a subprocess run of `python -m tool_schema_lint -` over stdin.
- **Agent integration example**: the trip-planner tools in `examples/agent_integration/` must stay valid for OpenAI strict mode and Gemini and within a 1,000-token budget.

Manual check: run the commands in [How to Run](#how-to-run) and compare with the outputs above.

---

## Known Limitations

- **Static analysis only.** It does not call any provider API, so a clean result means "matches the documented rules", not "guaranteed to be accepted". Providers change their rules; the sources and the date they were checked are listed above, and each rule's source is shown by `--list-rules`.
- **OpenAI function-name rule (O001)** is based on the API's validation error message (`^[a-zA-Z0-9_-]{1,64}$`), not a dedicated page in OpenAI's guides. Evidence: [an OpenAI community report quoting the 400 error](https://community.openai.com/t/openai-badrequesterror-error-code-400-does-not-match-a-za-z0-9-1-64/709823).
- **Gemini keyword rules (GM003-GM005)** describe the `parameters` field (Gemini's `Schema` object). Tools read from `parametersJsonSchema` skip them. When MCP or OpenAI tools are linted with `--target gemini`, they are assumed to be sent as `parameters`; if your SDK sends `parametersJsonSchema`, disable those rules. `$ref` / `$defs` are not flagged for Gemini because the SDK resolves them.
- **OpenAI strict nesting depth (S006)** counts levels of nested object schemas; OpenAI does not publish its exact counting method.
- **Description checks (G004, G005, A002) are heuristics**: length, placeholder words, sentence count. They are warnings or info and can be disabled.
- **Token counts are estimates** (compact JSON characters / 4), not a provider tokenizer; providers also add their own framing around tool definitions.
- `$ref` is checked only within the same document; remote references are reported, not fetched.
- Input files larger than 20 MB are rejected.
- Tested on Windows 11 with Python 3.11.0. The code is platform-independent standard-library Python, but Linux/macOS and Python 3.10 were not tested for this contribution.

---

## Security & Privacy Considerations

- **Secrets Handling**: No credentials are needed or read. The tool reads no environment variables.
- **Data Privacy**: Everything runs locally. The tool makes no network requests and sends nothing to any service; input is only read and printed back in findings.
- **Safety**: It never executes code from its input and never writes files. JSON input is parsed with Python's `json` module; schemas are traversed iteratively and `$ref` is never followed, so recursive schemas cannot cause infinite loops. Input size is capped at 20 MB and pathologically nested JSON is rejected with exit code `2`.

---

## Future Improvements

- [ ] Connect to a running MCP server (stdio / HTTP) and lint `tools/list` directly.
- [ ] SARIF output for GitHub code scanning.
- [ ] `--fix` for mechanical issues (add `additionalProperties: false`, rename invalid names).
- [ ] Optional model-assisted rewrite suggestions for weak descriptions.
- [ ] Lint `outputSchema` and Anthropic `input_examples` against the input schema.

---

## License

*This project is contributed under the repository's open-source license (MIT).*
