# token-cost-estimator

> A CLI tool that counts tokens and estimates the API cost of any prompt across Gemini models — before you make a single API call. No surprise bills.

---

## Overview

### Problem Statement & Intended Users

When building with the Gemini API, developers have no way to know how many tokens a prompt will consume or how much it will cost until after the API call completes. This is painful for:

- Long prompts (research documents, code files, video generation scripts)
- Batch jobs running hundreds of prompts
- Teams working within a fixed API budget

By the time you see the bill, the tokens are already spent.

**token-cost-estimator** solves this by checking the cost of any prompt *before* sending it. It uses Google's `count_tokens` endpoint — completely free, no generation, no charges — to give an exact input token count and a projected total cost.

**Intended Users**: Developers and AI engineers building with the Google Gemini API who want visibility into token usage and cost during development.

### Key Features

| Feature | Flag | Description |
|---|---|---|
| Token count + cost estimate | *(default)* | Exact input tokens via Gemini API + projected output cost |
| Multi-model comparison | `--all-models` | Run the same prompt across all models side by side |
| Pricing table | `--list-models` | View all models, prices, and token count API support |
| JSON output | `--json` | Machine-readable output for scripting or CI pipelines |
| Budget guard | `--budget` | Warn and exit with code 1 when cost exceeds your limit |
| File input | `--file` | Read prompt from any text file |
| Batch mode | `--batch` | Process all `.txt` files in a folder, show per-file + total cost |
| Token breakdown | *(auto)* | For prompts over 1000 tokens, shows character/word/token breakdown |

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Core Library**: `google-genai` (official Google Gemini Python SDK)
- **Models Supported**: `gemini-3.8-flash`, `gemini-3.8-flash-lite`
- **External APIs**: Google Gemini `count_tokens` endpoint — free, no generation, no output tokens billed

---

## Architecture & Data Flow

```
[User Input]
  CLI argument / --file / --batch folder / stdin
        |
        v
[Argument Parser]
  validates flags, loads prompt(s)
        |
        v
[count_tokens API call]
  Google Gemini endpoint — returns exact input token count
  (if prompt >= 1000 tokens, breakdown is added automatically)
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
- A Gemini API key — get one free at https://aistudio.google.com/apikey (no credit card needed)

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

4. **Configure your API key:**
   ```bash
   cp .env.example .env
   # Open .env and replace the placeholder with your real Gemini API key
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes | *None* | Your Gemini API key from aistudio.google.com |

---

## How to Run

```bash
# Basic estimate — inline prompt, default model (gemini-3.8-flash)
python main.py "Summarize the French Revolution in 3 bullet points"

# Use a specific model
python main.py "Explain quantum entanglement" --model gemini-3.8-flash-lite

# Set a custom estimated output token count (default is 500)
python main.py "Write a 500-word blog post about AI" --output-tokens 700

# Read prompt from a file
python main.py --file my_prompt.txt

# Compare cost across ALL supported models at once
python main.py "Translate this paragraph to Spanish" --all-models

# List all models with pricing and token count API support
python main.py --list-models

# Output as JSON — for scripts, CI pipelines, or saving to file
python main.py "Explain what a neural network is" --json

# Set a budget — warns and exits with code 1 if cost exceeds it
python main.py "Explain what a neural network is" --budget 0.01

# Batch mode — estimate cost for all .txt files in a folder
python main.py --batch prompts/

# Batch with budget guard
python main.py --batch prompts/ --budget 0.05

# Batch as JSON
python main.py --batch prompts/ --json
```

---

## Example Input & Output

### Basic estimate
```bash
python main.py "Explain what a neural network is"
```
```
Model    : gemini-3.8-flash
--------------------------------------------------
Input tokens   : 7
Output tokens  : 500 (estimated)
Input cost     : $0.000001
Output cost    : $0.000200
Total cost     : $0.000201
--------------------------------------------------
```

### Token breakdown (auto-triggered for prompts over 1000 tokens)
```bash
python main.py --file large_prompt.txt
```
```
Model    : gemini-3.8-flash
--------------------------------------------------
  Prompt breakdown (large prompt detected):
    Characters : 8,794
    Words      : 1,305
    Tokens     : 2,448
Input tokens   : 2,448
Output tokens  : 500 (estimated)
Input cost     : $0.000245
Output cost    : $0.000200
Total cost     : $0.000445
--------------------------------------------------
```

### Batch mode
```bash
python main.py --batch prompts/
```
```
Batch mode — processing 3 file(s) from 'prompts/'

File: prompt1.txt
Model    : gemini-3.8-flash
--------------------------------------------------
Input tokens   : 9,  Total cost : $0.000201
--------------------------------------------------

File: prompt2.txt
...

==================================================
BATCH SUMMARY
==================================================
Files processed   : 3
Total input tokens: 32
Total est. cost   : $0.000603
==================================================
```

### Batch as JSON
```bash
python main.py --batch prompts/ --json
```
```json
{
  "model": "gemini-3.8-flash",
  "files_processed": 3,
  "total_input_tokens": 32,
  "total_estimated_cost": 0.000603,
  "results": [
    { "file": "prompt1.txt", "input_tokens": 9, "total_cost": 0.000201 },
    { "file": "prompt2.txt", "input_tokens": 10, "total_cost": 0.000201 },
    { "file": "prompt3.txt", "input_tokens": 13, "total_cost": 0.000201 }
  ]
}
```

### `--json` output
```bash
python main.py "Explain what a neural network is" --json
```
```json
{
  "model": "gemini-3.8-flash",
  "input_tokens": 7,
  "output_tokens": 500,
  "input_cost": 1e-06,
  "output_cost": 0.0002,
  "total_cost": 0.000201
}
```

### `--budget` guard
```bash
python main.py "Explain what a neural network is" --budget 1.0
# OK: Estimated cost is within budget of $1.000000

python main.py "Explain what a neural network is" --budget 0.000001
# WARNING: Estimated cost $0.000201 exceeds budget of $0.000001
```

### `--list-models`
```
Supported models and pricing (per 1M tokens):

Model                               Input     Output  Token Count API
-----------------------------------------------------------------
gemini-3.8-flash               $   0.100 $   0.400  native
gemini-3.8-flash-lite          $   0.075 $   0.300  via gemini-3.8-flash
```

---

## How to Test

```bash
# 1. List models — no API key needed
python main.py --list-models

# 2. Basic estimate
python main.py "Hello world"

# 3. JSON output — verify it is valid
python main.py "Explain what a neural network is" --json | python3 -m json.tool

# 4. Budget pass
python main.py "Explain what a neural network is" --budget 1.0

# 5. Budget warning
python main.py "Explain what a neural network is" --budget 0.000001

# 6. All models
python main.py "Explain what a neural network is" --all-models

# 7. Token breakdown — use a large file (e.g. README.md itself)
python main.py --file README.md

# 8. Batch mode
mkdir test_prompts
echo "Explain what a neural network is." > test_prompts/p1.txt
echo "Summarize the history of AI." > test_prompts/p2.txt
echo "What is supervised learning?" > test_prompts/p3.txt
python main.py --batch test_prompts/
python main.py --batch test_prompts/ --budget 0.01
python main.py --batch test_prompts/ --json
rm -rf test_prompts/
```

---

## Known Limitations

- Output token count is an estimate supplied by the user via `--output-tokens` (default 500). Only input tokens are counted exactly.
- `gemini-3.8-flash-lite` does not natively support `count_tokens`; token count is approximated using `gemini-3.8-flash` (tokenizers are compatible).
- Batch mode only reads `.txt` files. Other formats (`.md`, `.pdf`) are not supported yet.
- Pricing is hardcoded. Check https://ai.google.dev/gemini-api/docs/pricing if rates have changed.
- Tested on macOS (Apple Silicon, Python 3.14). Windows support should work but is not fully verified.

---

## Security & Privacy Considerations

- **Secrets Handling**: API key loaded from `.env` via `python-dotenv`. Never hardcode keys in source files.
- **Data Privacy**: Prompt text is sent to Google's `count_tokens` endpoint. Do not use with confidential content.
- **Safety**: Read-only — calls only the token counting endpoint. No text is generated or stored.

---

## Future Improvements

- [ ] Support Anthropic and OpenAI models
- [ ] Batch mode support for `.md` and `.pdf` files
- [ ] Fetch live pricing from a remote source to stay current automatically
- [ ] Per-model budget breakdown when used with `--all-models`
- [ ] `--output-file` flag to save JSON results directly to disk

---

## License

*This project is contributed under the repository's open-source license.*
