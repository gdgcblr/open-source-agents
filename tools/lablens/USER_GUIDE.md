# Run LabLens on your computer

This guide is for anyone who wants to install and run LabLens from a fresh clone.
The deterministic lab-range comparison works without an AI model. Ollama and Gemma
are optional and run locally on your computer.

## Requirements

- Python 3.10 or newer
- Git
- Optional for local AI: [Ollama](https://ollama.com/download)

No API key or cloud AI account is needed.

## 1. Get the project

Clone the repository and move into the LabLens folder:

```powershell
git clone https://github.com/gdgcblr/open-source-agents.git
Set-Location open-source-agents\tools\lablens
```

If you already have a clone, change directory to its `tools\lablens` folder.

## 2. Install Python dependencies

Create and activate a virtual environment, then install the dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `py` is not available, use `python` in place of `py` to create the environment.
On macOS or Linux, activate it with `source .venv/bin/activate`.

## 3. Start LabLens

From the `tools\lablens` directory, run:

```powershell
streamlit run app.py
```

Streamlit opens LabLens in your browser. Select a supported test, enter the result
and unit shown on your report, and use the reference interval printed by your lab.
The prefilled interval is an illustrative example, not a universal medical range.
Select **Explain my result** to see the comparison and questions to discuss with
a healthcare professional.

### Example

For practice only, a TSH value of `5.0 mIU/L` compared with an entered interval
of `0.4–4.0 mIU/L` is reported as **Above supplied range**. LabLens explains that
this comparison alone cannot explain the cause or determine whether the result
is concerning. Use the interval from your own report; this example is not medical
advice.

## Optional: enable local AI with Gemma

1. Install Ollama from [ollama.com/download](https://ollama.com/download) and start
   the Ollama application.
2. In a separate PowerShell window, download Gemma:

   ```powershell
   ollama pull gemma3:4b
   ```

3. Start LabLens using the command above. After submitting a result, choose
   **Simplify with local AI**.

Ollama must be available at `http://127.0.0.1:11434`. If it is not running, start
the Ollama application or run `ollama serve`. If the model is missing, run
`ollama pull gemma3:4b` and retry. You can choose a different installed Ollama
model under **Advanced settings**.

AI is optional. It receives only the selected test, result, unit, and entered
reference interval, and has no cloud fallback. Its explanation may be inaccurate;
it is educational, not a diagnosis or substitute for professional care. If AI is
unavailable or blocked, the deterministic comparison remains available.

## Run the tests

With the virtual environment active, run from this directory:

```powershell
python -m unittest discover -s tests -v
```

The suite mocks Ollama, so tests do not require a downloaded model or a running
Ollama service.

## Troubleshooting

- **`py` is not recognized:** Install Python 3.10+ and enable the Python launcher,
  or use `python` instead of `py`.
- **`streamlit` is not recognized:** Activate the virtual environment and install
  packages with `python -m pip install -r requirements.txt`.
- **Ollama is unavailable:** Start Ollama locally; LabLens's standard comparison
  does not depend on it.
- **The model is not found:** Run `ollama pull gemma3:4b`, or pull the selected
  model name from Advanced settings.

For safety, privacy, and project details, see [README.md](./README.md).
