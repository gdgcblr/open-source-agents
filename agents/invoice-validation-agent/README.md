# Invoice Validation Agent

Deterministic invoice validation with optional local Ollama or cloud Gemini explanations. The deterministic result is always the source of truth: explanations cannot alter `APPROVED`/`REJECTED`, invent fields, or authorize payment.

## Data flow

`Invoice JSON -> validate_invoice() -> structured result -> optional explanation -> JSON output`

The base validator uses only Python's standard library. AI integrations are lazy and optional.

## Install

```bash
cd agents/invoice-validation-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

Install `google-genai` for Gemini or `google-adk` for the optional ADK entry point; both are optional.

## CLI

```bash
python main.py --case valid
python main.py --case duplicate
python main.py --case mismatch
python main.py --case mismatch --explain --provider ollama
python main.py --input invoice.json --explain --provider gemini
```

To validate a JSON file:

```bash
python main.py --input invoice.json
```

The input file must contain an `invoice` object and may include `known_invoices`. With `--explain`, `ai_explanation` is separate from the deterministic result.

## Example Input & Output

## Ollama

Install Ollama and obtain a model separately (Python never downloads models):

```bash
ollama pull gemma3:1b
export OLLAMA_MODEL=gemma3:1b
python main.py --case mismatch --explain --provider ollama
```

`OLLAMA_BASE_URL` defaults to `http://localhost:11434`; invoice data stays local with Ollama.

A duplicate invoice or incorrect total returns `"status": "REJECTED"` with a specific issue code.

## Gemini and ADK

```bash
pip install google-genai
export GEMINI_API_KEY='your-key'
export GEMINI_MODEL=gemini-2.5-flash
python main.py --case mismatch --explain --provider gemini
```

Cloud processing sends invoice data to Google; keys are never printed. Install `google-adk` and use `adk_agent.py` as the separate ADK app entry point. Its tool calls the same deterministic validator and the base suite does not claim an ADK runtime test without that optional package and credentials.

## Testing and limitations

```bash
python -m pytest -v
python run_governance.py
python -m compileall -q .
```

The governance runner emits machine-readable JSON with case IDs, policies, expected/actual outcomes, and summary counts. It covers decision integrity, grounded explanations, prompt-injection resilience, required fields, dates, amounts, duplicates, and totals. It is an offline deterministic harness; it is not certification, comprehensive safety testing, or regulatory compliance. AI failures preserve validation output. PDF extraction, external PO verification, and database lookup are not implemented. An approved result is not payment authorization.

The normal test suite requires no credentials, network, or live model. Ollama and Gemini integrations are implemented but live end-to-end calls are environment-dependent and were not exercised by the offline suite. ADK is isolated and likewise requires installing `google-adk` and configuring its runtime.

## Security and privacy

Invoice content is untrusted data, never an instruction source. Ollama is local only when `OLLAMA_BASE_URL` points to a local server. Gemini processing may transmit invoice data to Google. Do not commit real invoices, credentials, `.env` files, or provider logs; API keys are not included in governance reports. Provider explanations cannot change deterministic status, issue codes, amounts, duplicate results, or authorize payment.

## License

This project is contributed under the repository's open-source license.
