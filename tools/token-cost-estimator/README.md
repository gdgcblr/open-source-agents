# token-cost-estimator

> A CLI tool that counts tokens and estimates the API cost of a prompt across Gemini models before you make a single API call.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Developers using Gemini APIs have no easy way to know how many tokens a prompt will consume or what it will cost before sending it — leading to surprise bills and wasted budget.
- **Intended Users**: Developers and AI engineers building with the Google Gemini API who want to estimate token usage and cost during development.

### Key Features
- Accurate token counting using Google's `count_tokens` API endpoint
- Cost estimation for both input and output tokens across current Gemini models
- Supports prompt input via CLI argument, file path, or stdin
- `--all-models` flag to compare cost across every supported model at once
- `--list-models` flag to view current pricing and token counting support at a glance

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
[Formatted report printed to stdout]
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
```

---

## Example Input & Output

### Example Input
```bash
python main.py "Explain what a neural network is" --model gemini-3.8-flash
```

### Example Output
```
Model    : gemini-3.8-flash
Prompt   : Explain what a neural network is
--------------------------------------------------
Input tokens   : 7
Output tokens  : 500 (estimated)
Input cost     : $0.000001
Output cost    : $0.000200
Total cost     : $0.000201
--------------------------------------------------
```

### With `--all-models`
```bash
python main.py "Explain what a neural network is" --all-models
```
```
Model    : gemini-3.8-flash
Prompt   : Explain what a neural network is
--------------------------------------------------
Input tokens   : 7
Output tokens  : 500 (estimated)
Input cost     : $0.000001
Output cost    : $0.000200
Total cost     : $0.000201
--------------------------------------------------

Model    : gemini-3.8-flash-lite
Prompt   : Explain what a neural network is
--------------------------------------------------
Input tokens   : 7
Output tokens  : 500 (estimated)
Input cost     : $0.000001
Output cost    : $0.000150
Total cost     : $0.000151
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

# 2. Test with a short inline prompt
python main.py "Hello world" --model gemini-3.8-flash

# 3. Test all models at once
python main.py "Explain what a neural network is" --all-models

# 4. Test file input
echo "Explain machine learning in simple terms." > test_prompt.txt
python main.py --file test_prompt.txt
```

---

## Known Limitations

- Output token count is an estimate provided by the user via `--output-tokens` (default 500). The tool cannot predict actual output length — only input tokens are counted precisely.
- `gemini-3.8-flash-lite` does not natively support the `count_tokens` endpoint; token count is approximated using `gemini-3.8-flash` (tokenizers are compatible).
- Pricing data is hardcoded based on Google's published rates and may drift if Google updates pricing. Check https://ai.google.dev/gemini-api/docs/pricing for the latest.
- Tested on macOS. Windows support via `.venv\Scripts\activate` should work but is not fully verified.

---

## Security & Privacy Considerations

- **Secrets Handling**: API key is loaded from a `.env` file via `python-dotenv`. Never hardcode keys in source files.
- **Data Privacy**: The prompt text is sent to Google's Gemini `count_tokens` API endpoint. Do not use this tool with confidential or sensitive prompt content in untrusted environments.
- **Safety**: This tool is read-only — it calls only the token counting endpoint, not the generation endpoint, so no text is generated or stored.

---

## Future Improvements

- [ ] Support Anthropic and OpenAI models
- [ ] Add a `--json` flag for machine-readable output
- [ ] Cache pricing data from a remote source to stay current automatically
- [ ] Add a `--budget` flag that warns when estimated cost exceeds a threshold

---

## License

*This project is contributed under the repository's open-source license.*
