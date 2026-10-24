# Prompt Cost Analyzer

> An MCP server that estimates text token usage and the maximum input/output cost for a model request.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Before running an LLM request, developers want to understand the text input size and a conservative cost bound based on their output-token setting.
- **Intended Users**: Developers building MCP-compatible clients and LLM workflows.

### Key Features
- Counts prompt and tool-result text using `cl100k_base`.
- Estimates input cost and maximum output cost from a user-provided output-token cap.
- Includes a small built-in price snapshot, with per-call user overrides and custom model rates.
- Exposes `estimate_prompt_cost` and `list_supported_models` as MCP tools.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: MCP Python SDK (`FastMCP`)
- **Models**: Provider-neutral; accepts built-in model identifiers or custom model names
- **External APIs / Tools**: None; analysis is local

---

## Architecture & Data Flow

The MCP client sends a prompt, any text tool results, a model identifier, and a maximum output-token count. The server tokenizes the text locally, resolves built-in or supplied per-million-token rates, and returns input and maximum completion cost estimates.

---

## Prerequisites

- Python 3.10+
- pip
- An MCP-compatible client

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/prompt-cost-analyzer
   ```

2. **Install the server:**
   ```bash
   uv venv --python 3.11
   source .venv/bin/activate
   python -m pip install -e .
   ```
   If you do not use `uv`, create the virtual environment with `python3.11 -m venv .venv` instead.

3. **Configure Environment Variables:**
   No API keys or environment variables are required. `.env.example` is included for consistency with the repository's tool structure. The first token-counting request may download the public `cl100k_base` tokenizer data if it is not already cached; prompt and tool-result text are not sent to the tokenizer host.

---

## Configuration & Environment Variables

No environment variables are required. Custom model prices can be passed to `estimate_prompt_cost` as USD per million tokens.

The built-in rates are a snapshot checked on **2026-10-24**:

| Model ID | Input USD / 1M tokens | Output USD / 1M tokens | Source |
| :--- | ---: | ---: | :--- |
| `claude-opus-4-6` | 5.00 | 25.00 | [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| `claude-sonnet-4-6` | 3.00 | 15.00 | [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| `claude-haiku-4-5` | 1.00 | 5.00 | [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| `gemini-3-pro-preview` | 2.00 | 10.00 | [Google AI pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| `gemini-3-flash-preview` | 0.75 | 3.75 | [Google AI pricing](https://ai.google.dev/gemini-api/docs/pricing) |

These are published standard paid-tier rates, not a live price feed. The Gemini rates include scheduled pricing periods noted by the provider; verify current rates before using the estimates for budgeting. Supply overrides for changed rates, other models, or a different pricing tier. Overriding one rate leaves the other built-in rate unchanged; unknown models require both rates.

---

## How to Run

Run the MCP server over stdio:

```bash
prompt-cost-analyzer
```

or:

```bash
python -m prompt_cost_analyzer.server
```

This process is expected to keep running and wait for an MCP client; silence in a standalone terminal is normal. Configure the MCP client to launch this command from the project directory (or use the installed console command). The server offers:

- `list_supported_models`: returns the built-in model rates and their sources.
- `estimate_prompt_cost`: accepts `prompt`, `model`, `max_output_tokens`, optional `tool_results` (a list of text strings), and optional `input_usd_per_million` / `output_usd_per_million` overrides.

### Test with VS Code

1. In the workspace root, create or open `.vscode/mcp.json` and add this server entry:

   ```json
   {
     "servers": {
       "prompt-cost-analyzer": {
         "type": "stdio",
         "command": "${workspaceFolder}/tools/prompt-cost-analyzer/.venv/bin/prompt-cost-analyzer"
       }
     }
   }
   ```

   If the tool is installed somewhere else, set `command` to the full path of its `prompt-cost-analyzer` executable. On Windows, use `.venv\\Scripts\\prompt-cost-analyzer.exe`.

2. Save the file, then start the server from the MCP server controls in VS Code. It should remain running; that is expected. If it fails to start, check the server output in VS Code and confirm the executable path and Python environment.

3. Before the first estimate, warm the tokenizer cache from the workspace root:

   ```bash
   tools/prompt-cost-analyzer/.venv/bin/python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"
   ```

   This may download tokenizer data and requires network access. Doing it outside the MCP call avoids a timeout while the first estimate initializes the tokenizer.

4. Open Copilot Chat, enable the server's tools using the tools picker, and ask it to call `list_supported_models`. Then test cost estimation with a request such as:

   > Call `estimate_prompt_cost` with prompt `Summarize the repository status.`, tool_results `["3 files changed; 2 tests passed."]`, model `claude-sonnet-4-6`, and max_output_tokens `500`.

   The returned object should include prompt/tool-result token counts, estimated input cost, maximum output cost, and the combined maximum estimate. Later requests use the local tokenizer cache.

---

## Example Input & Output

### Example Input

```json
{
  "prompt": "Summarize the repository status.",
  "tool_results": ["3 files changed; 2 tests passed."],
  "model": "claude-sonnet-4-6",
  "max_output_tokens": 500
}
```

### Example Output

```json
{
  "model": "claude-sonnet-4-6",
  "tokenizer": "cl100k_base (approximation; provider tokenizers may differ)",
  "prompt_tokens": 7,
  "tool_result_tokens": 11,
  "estimated_input_tokens": 18,
  "max_output_tokens": 500,
  "input_usd_per_million": 3.0,
  "output_usd_per_million": 15.0,
  "estimated_input_cost_usd": 0.000054,
  "max_output_cost_usd": 0.0075,
  "maximum_estimated_cost_usd": 0.007554,
  "pricing_source": "https://platform.claude.com/docs/en/about-claude/pricing",
  "pricing_note": "Standard input and output rates; cached tokens are not included.",
  "assumptions": [
    "The maximum cost assumes every allowed output token is generated.",
    "Provider message framing, tool schemas, caching, images, audio, and other non-text charges are not included.",
    "Pricing is a snapshot; confirm current provider rates before budgeting."
  ]
}
```

---

## How to Test

From this directory, run:

```bash
pip install -e .
python -m unittest discover -s tests -v
```

---

## Known Limitations

- `cl100k_base` is a convenient local tokenizer, not an exact tokenizer for every supported provider/model. Provider-side token counts can differ.
- Only the supplied prompt and text tool results are counted. Message framing, system/client-added content, tool schemas, multimodal inputs, and provider-specific token additions are not included.
- The output estimate uses the full configured maximum, so it is a cost ceiling for the text-token calculation, not a prediction of actual generation.
- Built-in pricing can become stale and does not account for caching, batch discounts, service tiers, taxes, or other provider-specific charges.
- Tool execution charges and any subsequent calls in an agent loop are not included; analyze each request separately.

---

## Security & Privacy Considerations

- **Secrets Handling**: No credentials are required or stored.
- **Data Privacy**: Prompt and tool-result text is processed locally and is not transmitted to an external service.
- **Safety**: The server does not execute prompts, tool results, or generated code.

---

## Future Improvements

- [ ] Support provider-native token counting where available.
- [ ] Add richer cost breakdowns for caching and additional pricing tiers.
- [ ] Add a way to update the built-in pricing snapshot.

---

## License

This project is contributed under the repository's open-source license.
