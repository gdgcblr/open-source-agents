# Agent Reality Check

> A small workshop-friendly evaluation tool for testing whether an AI agent behaves responsibly in ambiguous, missing-information, and high-impact situations.

---

## What this project is

This project is a lightweight safety-check harness for AI agents.

It gives an agent a few realistic prompts and then checks whether the answer:
- asks the right clarifying question
- avoids guessing when information is missing
- stops before risky or destructive actions
- does not claim an action that was never actually done

It is a testing application, not a production safety system.

---

## Core idea

The project is best described as:

> a CLI evaluation tool that runs scenario tests against an AI provider and reports PASS, FAIL, or INCONCLUSIVE results.

The default mock provider works fully offline. The Ollama provider is optional and requires a separate local Ollama installation and model download.

---

## Requirements

- Python 3.10 or newer
- A fresh virtual environment
- Optional: Ollama installed locally if you want to test a live model

No API key is required for the default mock-provider demo.

---

## Quick install

### macOS / Linux

```bash
cd /path/to/agent-reality-check
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

### Windows (PowerShell)

```powershell
cd C:\path\to\agent-reality-check
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

### Windows (cmd)

```cmd
cd C:\path\to\agent-reality-check
py -3 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

---

## Run the mock demo (works offline)

After installation, you can run the built-in offline demo without Ollama, API keys, or internet access for the model logic:

```bash
agent-reality-check --provider mock --report reports/mock_report.json
```

You can also run it with Python directly:

```bash
python -m agent_reality_check.cli --provider mock --report reports/mock_report.json
```

This is the recommended first demo for a new developer.

---

## Optional Ollama setup

Ollama is optional and is not required for the default offline demo.

If you want to test a live local model, install Ollama separately and download a model such as `llama3.2:3b`:

```bash
ollama pull llama3.2:3b
```

Then run:

```bash
agent-reality-check --provider ollama --report reports/ollama_report.json
```

or

```bash
python -m agent_reality_check.cli --provider ollama --report reports/ollama_report.json
```

This path requires the local Ollama service and model to be installed on the machine.

---

## Run the tests

```bash
pytest -q
```

The suite checks core scenario behavior and packaging assumptions.

---

## Notes

- The project supports a clean install in a fresh Python virtual environment starting at Python 3.10.
- The mock provider is the deterministic, offline path.
- The Ollama path is intentionally optional and separate from the core install.
- The project is intended for evaluation and workshop use, not as a production safety guarantee.

---

## License

This project is contributed under the repository's open-source license.
