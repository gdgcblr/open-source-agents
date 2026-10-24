# token-cost-estimator

> A CLI tool that counts tokens and estimates the API cost of any prompt across Gemini and OpenAI models — before you make a single API call. No surprise bills.

---

## Overview

### Problem Statement & Intended Users

When building with any LLM API — Gemini, OpenAI, Anthropic, or others — developers have no way to know how many tokens a prompt will consume or how much it will cost until after the API call completes. This is painful for:

- Long prompts (research documents, code files, video generation scripts)
- Batch jobs running hundreds of prompts
- Teams working within a fixed API budget

By the time you see the bill, the tokens are already spent.

**token-cost-estimator** solves this by checking the cost of any prompt *before* sending it. This version supports Google Gemini (via the free `count_tokens` API) and OpenAI (via local `tiktoken` — no API key needed), with more providers planned.

**Intended Users**: Developers and AI engineers building with Gemini or OpenAI APIs who want visibility into token usage and cost during development.

### Key Features

| Feature | Flag | Description |
|---|---|---|
| Token count + cost estimate | *(default)* | Exact input tokens + projected output cost |
| Multi-provider support | `--provider` | Switch between `gemini` and `openai` |
| Multi-model comparison | `--all-models` | Compare cost across all models for the selected provider |
| Pricing table | `--list-models` | View all models, prices, and token count method |
| JSON output | `--json` | Machine-readable output for scripting or CI pipelines |
| Budget guard | `--budget` | Warn + exit code 1 when cost exceeds your limit |
| File input | `--file` | Read prompt from any text file |
| Batch mode | `--batch` | Process all `.txt` files in a folder, show per-file + total cost |
| Token breakdown | *(auto)* | Prompts over 1000 tokens automatically show character/word/token breakdown |

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Core Libraries**: `google-genai` (Gemini SDK), `tiktoken` (OpenAI local tokenizer), `python-dotenv`
- **Providers Supported**: Google Gemini, OpenAI
- **Token Counting**:
  - Gemini: Google's `count_tokens` API endpoint (free, no generation)
  - OpenAI: `tiktoken` local tokenizer (no API key needed, runs offline)

---

## Architecture & Data Flow

```
[User Input]
  CLI argument / --file / --batch folder / stdin
        |
        v
[Argument Parser]
  selects provider (gemini / openai), validates model
        |
        v
[Token Counter]
  Gemini  → count_tokens API (free endpoint)
  OpenAI  → tiktoken local tokenizer (no API call)
  (if tokens >= 1000, breakdown added automatically)
        |
        v
[Cost Calculator]
  applies per-model pricing (input + estimated output)
  batch mode: aggregates total across all files
        |
        v
[Output]
  formatted report  OR  JSON (--json)
  budget check triggered if --budget is set
```

---

## Prerequisites

- Python 3.10+
- `pip`
- A Gemini API key (only needed for Gemini provider) — get one free at https://aistudio.google.com/apikey
- No API key needed for OpenAI provider — uses local `tiktoken`

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/token-cost-estimator
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate      # macOS/Linux
   .venv\Scripts\activate         # Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your API key (Gemini only):**
   ```bash
   cp .env.example .env
   # Open .env and replace the placeholder with your real Gemini API key
   # Skip this step if you only want to use the OpenAI provider
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Only for Gemini | *None* | Your Gemini API key from aistudio.google.com |

---

## How to Run

```bash
# Gemini — basic estimate (default provider)
python main.py "Summarize the French Revolution in 3 bullet points"

# OpenAI — no API key needed
python main.py "Summarize the French Revolution in 3 bullet points" --provider openai

# Use a specific model
python main.py "Explain quantum entanglement" --provider openai --model gpt-4o
python main.py "Explain quantum entanglement" --provider gemini --model gemini-3.8-flash-lite

# Compare all models for a provider
python main.py "Explain what a neural network is" --provider openai --all-models
python main.py "Explain what a neural network is" --provider gemini --all-models

# List all models and pricing for both providers
python main.py --list-models

# Set custom estimated output tokens (default: 500)
python main.py "Write a blog post about AI" --output-tokens 1000

# JSON output for scripting
python main.py "Explain what a neural network is" --provider openai --json

# Budget guard
python main.py "Explain what a neural network is" --provider openai --budget 0.01

# Read prompt from a file
python main.py --file my_prompt.txt --provider openai

# Batch mode — estimate all .txt files in a folder
python main.py --batch prompts/ --provider openai
python main.py --batch prompts/ --provider gemini --budget 0.05
```

---

## Example Input & Output

### Gemini estimate
```bash
python main.py "Explain what a neural network is" --provider gemini
```
```
Provider : gemini
Model    : gemini-3.8-flash
--------------------------------------------------
Input tokens   : 7
Output tokens  : 500 (estimated)
Input cost     : $0.000001
Output cost    : $0.000200
Total cost     : $0.000201
--------------------------------------------------
```

### OpenAI estimate — no API key needed
```bash
python main.py "Explain what a neural network is" --provider openai
```
```
Provider : openai
Model    : gpt-4o-mini
--------------------------------------------------
Input tokens   : 6
Output tokens  : 500 (estimated)
Input cost     : $0.000001
Output cost    : $0.000300
Total cost     : $0.000301
--------------------------------------------------
```

### OpenAI `--all-models`
```bash
python main.py "Explain what a neural network is" --provider openai --all-models
```
```
Provider : openai  Model : gpt-4o        Total cost : $0.005015
Provider : openai  Model : gpt-4o-mini   Total cost : $0.000301
Provider : openai  Model : gpt-4-turbo   Total cost : $0.015070
Provider : openai  Model : gpt-3.5-turbo Total cost : $0.000754
```

### Token breakdown (auto on prompts over 1000 tokens)
```bash
python main.py --file large_prompt.txt --provider gemini
```
```
  Prompt breakdown (large prompt detected):
    Characters : 8,794
    Words      : 1,305
    Tokens     : 2,448
Input tokens   : 2,448
Total cost     : $0.000445
```

### Batch mode
```bash
python main.py --batch prompts/ --provider openai
```
```
Batch mode — processing 3 file(s) from 'prompts/'
...
==================================================
BATCH SUMMARY
==================================================
Files processed   : 3
Total input tokens: 19
Total est. cost   : $0.000903
==================================================
```

### `--list-models`
```
--- Gemini models (requires GEMINI_API_KEY) ---
gemini-3.8-flash          $   0.100 $   0.400  API (native)
gemini-3.8-flash-lite     $   0.075 $   0.300  API (via gemini-3.8-flash)

--- OpenAI models (no API key needed — local tiktoken) ---
gpt-4o                    $   2.500 $  10.000  local (tiktoken)
gpt-4o-mini               $   0.150 $   0.600  local (tiktoken)
gpt-4-turbo               $  10.000 $  30.000  local (tiktoken)
gpt-3.5-turbo             $   0.500 $   1.500  local (tiktoken)
```

### `--json` output
```bash
python main.py "Explain what a neural network is" --provider openai --json
```
```json
{
  "provider": "openai",
  "model": "gpt-4o-mini",
  "input_tokens": 6,
  "output_tokens": 500,
  "input_cost": 9e-07,
  "output_cost": 0.0003,
  "total_cost": 0.000301
}
```

---

## How to Test

```bash
# 1. List all models — no API key needed
python main.py --list-models

# 2. OpenAI estimate — no API key needed
python main.py "Hello world" --provider openai

# 3. OpenAI all models
python main.py "Explain what a neural network is" --provider openai --all-models

# 4. OpenAI JSON — verify valid JSON
python main.py "Explain what a neural network is" --provider openai --json | python3 -m json.tool

# 5. Gemini estimate
python main.py "Explain what a neural network is" --provider gemini

# 6. Budget pass
python main.py "Explain what a neural network is" --provider openai --budget 1.0

# 7. Budget warning
python main.py "Explain what a neural network is" --provider openai --budget 0.000001

# 8. Token breakdown — use a large file
python main.py --file README.md --provider openai

# 9. Batch mode
mkdir test_prompts
echo "Explain what a neural network is." > test_prompts/p1.txt
echo "Summarize the history of AI." > test_prompts/p2.txt
echo "What is supervised learning?" > test_prompts/p3.txt
python main.py --batch test_prompts/ --provider openai
python main.py --batch test_prompts/ --provider openai --budget 0.01
python main.py --batch test_prompts/ --provider openai --json
rm -rf test_prompts/
```

---

## Known Limitations

- Output token count is an estimate supplied by the user via `--output-tokens` (default 500). Only input tokens are counted exactly.
- `gemini-3.8-flash-lite` does not natively support `count_tokens`; approximated using `gemini-3.8-flash`.
- Batch mode only reads `.txt` files. Other formats (`.md`, `.pdf`) not yet supported.
- Pricing is hardcoded. Check https://ai.google.dev/gemini-api/docs/pricing and https://openai.com/pricing for the latest rates.
- Anthropic support is planned but not yet implemented.
- Tested on macOS (Apple Silicon, Python 3.14). Windows support should work but is not fully verified.

---

## Security & Privacy Considerations

- **Secrets Handling**: API key loaded from `.env` via `python-dotenv`. Never hardcode keys in source files.
- **Data Privacy**: Gemini prompts are sent to Google's `count_tokens` endpoint. OpenAI token counting is fully local — no data leaves your machine.
- **Safety**: Read-only — no text is generated or stored by this tool.

---

## Future Improvements

- [ ] Add Anthropic provider support
- [ ] Batch mode support for `.md` and `.pdf` files
- [ ] Fetch live pricing from a remote source to stay current automatically
- [ ] `--output-file` flag to save JSON results directly to disk
- [ ] Per-model budget breakdown when used with `--all-models`

---

## License

*This project is contributed under the repository's open-source license.*
