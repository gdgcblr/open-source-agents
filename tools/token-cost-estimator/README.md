# token-cost-estimator

> A CLI tool that counts tokens and estimates the API cost of a prompt across Gemini models before you make a single API call — no surprise bills.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Before sending a prompt to the Gemini API, developers have no way to know how many tokens it will consume or how much it will cost. The bill only shows up after the call completes — which is especially painful for long prompts like video generation scripts, research documents, or large context windows.
- **Intended Users**: Developers and AI engineers building with the Google Gemini API who want to estimate token usage and cost during development.

### Key Features
- Accurate token counting using Google's `count_tokens` API endpoint (free, no generation)
- Cost estimation for both input and output tokens across current Gemini models
- Supports prompt input via CLI argument, file path, or stdin
- `--all-models` flag to compare cost across every supported model at once
- `--list-models` flag to view current pricing and token counting support at a glance
- `--json` flag for machine-readable output — pipe into scripts or save to file
- `--budget` flag to warn when estimated cost exceeds a set limit

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Core Library**: `google-genai` (official Google Gemini Python SDK)
- **Models Supported**: gemini-3.8-flash, gemini-3.8-flash-lite
- **External APIs**: Google Gemini `count_tokens` endpoint (no generation — no output tokens billed)

---

## Architecture & Data Flow

```
[User Input (CLI / file / stdin)]
        |
        v
[main.py argument parser]
        |
        v
[Google Gemini count_tokens API] --> returns exact input token count
        |
        v
[Cost calculator] --> applies per-model pricing
        |
        v
[Formatted report or JSON printed to stdout]
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
# Estimate cost for an inline prompt (default model: gemini-3.8-flash)
python main.py "Summarize the French Revolution in 3 bullet points"

# Use a specific model
python main.py "Explain quantum entanglement" --model gemini-3.8-flash-lite

# Estimate with a custom expected output token count
python main.py "Write a 500-word blog post about AI" --output-tokens 700

# Read prompt from a file
python main.py --file my_prompt.txt

# Compare cost across ALL models at once
python main.py "Translate this paragraph to Spanish" --all-models

# List all supported models and their pricing
python main.py --list-models

# Output results as JSON (great for scripting)
python main.py "Explain what a neural network is" --json

# Warn if estimated cost exceeds a budget (in USD)
python main.py "Explain what a neural network is" --budget 0.01

# Combine: all models + budget check
python main.py "Explain what a neural network is" --all-models --budget 0.001
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

### With `--json`
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

### With `--budget`
```bash
python main.py "Explain what a neural network is" --budget 1.0
```
```
Total cost     : $0.000201
OK: Estimated cost is within budget of $1.000000
```
```bash
python main.py "Explain what a neural network is" --budget 0.000001
```
```
Total cost     : $0.000201
WARNING: Estimated cost $0.000201 exceeds budget of $0.000001
```

### With `--all-models`
```bash
python main.py "Explain what a neural network is" --all-models
```
```
Model    : gemini-3.8-flash
--------------------------------------------------
Input tokens   : 7, Total cost : $0.000201
--------------------------------------------------

Model    : gemini-3.8-flash-lite
--------------------------------------------------
Input tokens   : 7, Total cost : $0.000151
--------------------------------------------------
```

### `--list-models` output
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
# 1. List models (no API call made)
python main.py --list-models

# 2. Test basic estimate
python main.py "Hello world" --model gemini-3.8-flash

# 3. Test JSON output and verify it is valid
python main.py "Explain what a neural network is" --json | python3 -m json.tool

# 4. Test budget pass
python main.py "Explain what a neural network is" --budget 1.0

# 5. Test budget warning
python main.py "Explain what a neural network is" --budget 0.000001

# 6. Test all models
python main.py "Explain what a neural network is" --all-models

# 7. Test file input
echo "Explain machine learning in simple terms." > test_prompt.txt
python main.py --file test_prompt.txt
```

---

## Known Limitations

- Output token count is an estimate provided by the user via `--output-tokens` (default 500). The tool cannot predict actual output length — only input tokens are counted precisely.
- `gemini-3.8-flash-lite` does not natively support the `count_tokens` endpoint; token count is approximated using `gemini-3.8-flash` (tokenizers are compatible).
- Pricing data is hardcoded based on Google's published rates and may drift if Google updates pricing. Check https://ai.google.dev/gemini-api/docs/pricing for the latest.
- Tested on macOS (Apple Silicon, Python 3.14). Windows support via `.venv\Scripts\activate` should work but is not fully verified.

---

## Security & Privacy Considerations

- **Secrets Handling**: API key is loaded from a `.env` file via `python-dotenv`. Never hardcode keys in source files.
- **Data Privacy**: The prompt text is sent to Google's Gemini `count_tokens` API endpoint. Do not use this tool with confidential or sensitive prompt content in untrusted environments.
- **Safety**: This tool is read-only — it calls only the token counting endpoint, not the generation endpoint, so no text is generated or stored.

---

## Future Improvements

- [ ] Support Anthropic and OpenAI models
- [ ] Cache pricing data from a remote source to stay current automatically
- [ ] Add a `--budget` per-model breakdown when used with `--all-models`

---

## License

*This project is contributed under the repository's open-source license.*
