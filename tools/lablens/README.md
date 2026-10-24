# LabLens — Lab Report Explainer

LabLens is a small local-first learning tool. It compares a numeric result with the reference interval entered from a report, explains the comparison deterministically, and optionally asks a local Ollama model for a simpler explanation.

## Use LabLens

The main flow is intentionally small:

1. Select a supported test and enter the result and unit printed on the report.
2. Enter the report's reference interval. The prefilled values are illustrative examples, not universal medical ranges.
3. Select **Explain my result** to see the deterministic comparison and questions to discuss with a clinician.
4. Optionally select **Simplify with local AI** to request a shorter explanation from Ollama running on your computer.

An assessment remains visible across Streamlit reruns. Editing any assessment input clears the previous result until you submit the new values. The local AI action is never automatic, and its response is displayed separately from the deterministic assessment.

## Safety and privacy

- The standard comparison works without AI and does not diagnose or recommend treatment.
- AI is optional. When used, the only model inputs are the selected test name, result, unit, and user-entered interval. The app does not accept report uploads or request identifying patient information.
- Ollama requests use a fixed `127.0.0.1:11434` endpoint. The app does not accept configurable remote endpoints and disables environment proxy use for this request.
- Inputs are allowlisted/bounded before processing. The AI system message and user data are sent as separate chat roles. AI output is length-limited and checked for common unsafe recommendations before display.
- Prompt instructions and output checks cannot guarantee safe or medically correct AI output. Treat AI as untrusted educational text and discuss personal interpretation with a qualified clinician.
- Lab reference intervals vary. Use the interval printed on the report; examples in the UI are illustrative only. A result within range does not rule out illness, and an out-of-range result does not establish a diagnosis.

## Requirements and run locally

- Python 3.10 or newer
- Optional: Ollama installed and running for local AI

For a fresh-clone, step-by-step setup and troubleshooting guide, see [USER_GUIDE.md](./USER_GUIDE.md).

From this directory in Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

If `py` is unavailable, use `python` to create the virtual environment instead.
Run these commands from `tools\lablens`.

To enable local AI on Windows:

1. Install Ollama from [ollama.com/download](https://ollama.com/download) and start the Ollama app.
2. In PowerShell, download the default model with `ollama pull gemma3:4b`.
3. Start LabLens with `streamlit run app.py` and leave Ollama running while using the **Simplify with local AI** button.

The model defaults to `gemma3:4b`. To use another Ollama model, open **Advanced settings** after an assessment and enter its name; pull that model first with `ollama pull <model-name>`. You can check installed models with `ollama list`. If the Ollama app is not running, start its local service with `ollama serve`. LabLens sends requests only to `127.0.0.1:11434`; it does not fall back to a cloud AI service.

If AI is unavailable, the app keeps the deterministic comparison visible and provides concise recovery steps in **Ollama setup help**. The deterministic comparison remains available without AI.

## Tests

Run from this directory:

```powershell
python -m unittest discover -s tests -v
```

The tests cover deterministic range comparison, input validation, prompt minimization, unsafe output rejection, local-only Ollama requests, common Ollama failures, and the Streamlit workflow (saved results, stale-result invalidation, validation errors, and optional-AI success and failure). UI tests mock Ollama and do not contact a running service.

## Project structure

```text
lablens/
├── app.py
├── ai/
│   └── ollama_client.py
├── application/
│   └── orchestrator.py
├── domain/
│   └── assessment.py
├── security/
│   └── guardrails.py
├── tests/
│   ├── test_app.py
│   └── test_assessment.py
├── requirements.txt
└── README.md
```

`app.py` is the UI; the orchestrator coordinates assessment and optional AI; assessment logic owns test metadata and deterministic comparisons; guardrails validate inputs and check AI output; the Ollama adapter only communicates with loopback Ollama.

See the parent repository's license and contribution requirements.
