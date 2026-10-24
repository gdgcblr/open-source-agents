# README Drafter

> An offline AI agent that inspects a project folder and drafts an accurate README for it, using a local Gemma model through Ollama. Your code never leaves your machine.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Writing a good README takes time, so many projects ship with none or with an outdated one. Cloud AI tools can help, but they require sending your source code to a third party.
- **Intended Users**: Developers and open-source contributors (including contributors to this repository, since the draft follows `template/README.md`) who want a solid first draft without uploading private code.

### Key Features
- **Grounded in the code**: Parses manifests (`pyproject.toml`, `requirements.txt`, `package.json`, `Cargo.toml`, `go.mod`, `Dockerfile`, `docker-compose.yml`, `Makefile`, `.env.example`) and reads the most important source files. Anything it cannot confirm becomes a `TODO:` instead of a guess.
- **Fully local**: Runs on Gemma 4 (`gemma4:e4b`) through Ollama. No API keys, no cloud calls.
- **Treats every project as untrusted**: Symlinks out of the project, `.git` metadata, `.env`, private keys and credential folders are never read. Passwords, tokens and keys are redacted before the model sees them. Every README is reviewed in code before it is shown or saved: download-and-run commands, tracking images and unverified links planted through prompt injection are removed and reported. See [Security & Privacy Considerations](#security--privacy-considerations).
- **Bounded context**: Sends the model at most ~30,000 characters of file content, so large repositories cannot overflow its context window.
- **Two ways to use it**: A chat UI (ADK Dev UI) where you can ask for revisions, or a one-shot CLI. Both save the draft to `output/README.draft.md`.
- **Runs anywhere with Docker**: `docker compose up` starts the agent and its own Ollama server.

---

## Technical Stack

- **Language & Runtime**: Python 3.12
- **Agent Framework**: [Google Agent Development Kit (ADK)](https://github.com/google/adk-python) 2.13.0
- **Model**: Gemma 4 `gemma4:e4b` via [Ollama](https://ollama.com) 0.40.10, connected through LiteLLM 1.106.2 (`ollama_chat` provider)
- **External APIs / Tools**: None. Everything runs locally.
- **Packaging**: Docker + Docker Compose (tested with OrbStack on macOS)

---

## Architecture & Data Flow

```
                 +-----------------------------------------------------------+
  "Draft a       |  ADK agent (readme_drafter)                               |
   README"  ---> |                                                           |
                 |  1. before_agent_callback: inspect_project()   (code)     |
                 |       - detect_project_stack: manifests, languages,       |
                 |         entry points, env var NAMES, license              |
                 |       - read_key_files: README, entry points, config,     |
                 |         source files nearest the root (30k char budget)   |
                 |       - every path checked by guardrails.safe_path,       |
                 |         every text passed through guardrails.redact       |
                 |                     |                                     |
                 |                     v                                     |
                 |  2. Gemma 4 (Ollama) writes the README from those facts,  |
                 |       which are marked as untrusted data                  |
                 |       optional tools: list_project_files, read_file       |
                 |       (capped at 4 tool calls / 6 model calls per turn)   |
                 |                     |                                     |
                 |                     v                                     |
                 |  3. after_model_callback: guardrails.review_readme        |
                 |       removes risky commands, unverified images/links     |
                 |       and secrets, then saves output/README.draft.md      |
                 +-----------------------------------------------------------+
```

**Why inspection happens in code, not as a tool call:** in testing, `gemma4:e4b` sometimes skipped a required first tool call and returned a placeholder README, or produced a malformed tool call that Ollama rejected. Gathering the facts deterministically and letting the model focus on writing made every run in the final test series succeed. The model still has `list_project_files` and `read_file` for follow-up questions.

**How big projects are handled:** the agent never sends the whole codebase. It sends the parsed manifests plus a ranked selection of files (existing README, entry points such as `main.py`/`index.ts`/`agent.py`, Docker/Makefile config, then source files closest to the project root) until a 30,000-character budget is used. Each file is capped at 8,000 characters. Files beyond the budget are listed by name only. On ADK's own source (815 Python files, 28 MB) the prompt stayed at ~8,400 tokens and the run took 19 seconds.

---

## Prerequisites

Pick one of the two setups.

**Option A: Docker (any OS)**
- Docker with Docker Compose v2 (Docker Desktop, OrbStack, or Docker Engine on Linux)
- ~10 GB free disk space (2.8 GB Ollama image + ~6.6 GB `gemma4:e4b` model)
- 16 GB RAM recommended

**Option B: Local Python**
- Python 3.12+
- [Ollama](https://ollama.com/download) 0.40+ with the model pulled: `ollama pull gemma4:e4b`

> Use a Gemma model with tool support. `gemma4` supports tools in Ollama; `gemma3` does not.

---

## Installation & Setup

### Option A: Docker
```bash
cd agents/readme-drafter
cp .env.example .env        # optional; edit PROJECT_DIR etc. there instead of exporting
```
The first `docker compose up` builds the agent image and downloads the model into a Docker volume.

### Option B: Local Python
```bash
cd agents/readme-drafter
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
ollama pull gemma4:e4b
```

---

## Configuration & Environment Variables

All variables are optional except `PROJECT_DIR` under Docker. Set them in your shell or in `agents/readme-drafter/.env` (read by Docker Compose, `adk web` and the CLI; shell variables win).

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `PROJECT_DIR` | Yes (Docker) | Current folder (local) | Absolute path of the project to document. Mounted read-only into the container. |
| `PROJECT_NAME` | No | Folder name | Project name to use in the README. Useful under Docker, where the folder is mounted as `/workspace`. |
| `MODEL_NAME` | No | `gemma4:e4b` | Ollama model tag. Must support tool calling. |
| `NUM_CTX` | No | `32768` | Context window (tokens) requested from Ollama. |
| `OLLAMA_API_BASE` | No | `http://localhost:11434` (local), `http://ollama:11434` (Docker) | Where the agent reaches Ollama. |
| `OUTPUT_DIR` | No | `./output` | Where `README.draft.md` is written. |

No API keys or secrets are needed.

---

## How to Run

### Docker: everything in containers (Linux, Windows, macOS)
```bash
PROJECT_DIR=/absolute/path/to/your/project docker compose up
```
Open http://localhost:8000, select `readme_drafter`, and type **"Draft a README for this project."**

### Docker on macOS: fast path using the Mac's GPU
Docker on macOS cannot use the Apple GPU, so the bundled Ollama runs on CPU and is slow. With Ollama installed on the Mac, run only the agent container:
```bash
PROJECT_DIR=/absolute/path/to/your/project \
OLLAMA_API_BASE=http://host.docker.internal:11434 \
docker compose up --no-deps readme-drafter
```

### One-shot CLI (no browser)
```bash
# Docker
PROJECT_DIR=/path/to/project docker compose run --rm readme-drafter python -m readme_drafter.cli

# Local Python
PROJECT_DIR=/path/to/project python -m readme_drafter.cli
PROJECT_DIR=/path/to/project python -m readme_drafter.cli "Focus on installation on Windows"
```

### Local Python: chat UI
```bash
PROJECT_DIR=/path/to/project adk web readme_drafter    # then open http://localhost:8000
```

The draft is saved to `output/README.draft.md`. In the chat UI you can ask for changes ("make the overview shorter", "add a Windows section"); each revised README is saved again.

---

## Example Input & Output

Genuine run on [`pypa/sampleproject`](https://github.com/pypa/sampleproject) (commit `621e497`) with its `README.md` deleted first, so the draft comes only from code and manifests. Local Python, `gemma4:e4b`, MacBook Pro (M5 Pro, 24 GB), under 10 seconds.

### Example Input
```bash
PROJECT_DIR=~/samples/sampleproject python -m readme_drafter.cli
```

### Example Output (`output/README.draft.md`, unedited)
````markdown
# sampleproject
A sample Python project.
## Overview
This project is a sample implementation intended to demonstrate usage patterns for a Python package.

**Key Features:**
*   Provides basic function definitions within its source structure.
*   Includes configuration checks for packaging, distribution, and testing readiness.

## Technical Stack
*   **Language/Runtime:** Python (requires Python >=3.9)
*   **Frameworks/Tools:** Peppercorn
*   **Dependencies:** `peppercorn`

## Architecture & Data Flow
The project structure contains source code within `src/sample/`, which exposes functionality like `add_one`. Testing and build processes are managed via `noxfile.py`, which utilizes tools such as `flake8`, `build`, and `twine`.

## Prerequisites
*   Python >=3.9

## Installation & Setup
To install the project (as defined in `pyproject.toml`):
```bash
pip install .
```

## Configuration & Environment Variables
No environment variables are explicitly defined or shown to be required in the provided files.

## How to Run
The project includes a sample script execution command defined in `pyproject.toml`:
```bash
sample
```

## Example Usage
The source code indicates a basic function:
```python
# In src/sample/simple.py
from sample import simple
result = simple.add_one(5)
# result will be 6
```
The `src/sample/__init__.py` shows an entry point with a print statement.

## How to Test
Testing is managed through the `noxfile.py` file, which supports running tests with `nox -s tests`.

## Known Limitations
*   TODO: Add specific limitations observed during development.

## Security & Privacy Considerations
TODO: Add security and privacy considerations.

## License
MIT (from LICENSE.txt)
````

Every fact above (Python >=3.9, the `peppercorn` dependency, the `sample` script, the nox sessions, the MIT license) comes from the project's files. The sections it could not verify are left as `TODO:` for the author.

---

## How to Test

**Unit tests** (27, no model or network needed). `tests/test_tools.py` covers manifest parsing, file selection, license detection and README extraction. `tests/test_security.py` builds a malicious project (symlinks to fake `~/.aws` and `~/.ssh` secrets, a password in `.git/config`, hard-coded passwords, a parser bomb) and checks that nothing leaks, that injected commands, images and links are removed, and that the loop limits hold:
```bash
python -m unittest discover -s tests -v
# or inside Docker:
PROJECT_DIR=$PWD docker compose run --rm --no-deps readme-drafter python -m unittest discover -s tests -v
```

**End-to-end check:**
1. Run the CLI against any project: `PROJECT_DIR=/path/to/project python -m readme_drafter.cli`
2. Confirm it prints `Saved to .../README.draft.md` and exits with code 0.
3. Open the draft and check that the commands and dependencies match the project.

---

## Known Limitations

- **Prompt injection is contained, not prevented**: In testing, `gemma4:e4b` followed instructions hidden in a project file in 3 of 3 runs despite being told not to, and wrote the attacker's `curl ... | bash` into the install steps. The code review removed it every time, but it can only catch known-dangerous patterns (download-and-run, destructive commands, unverified links, secrets). An injection that makes the model describe the project wrongly, in plain words, cannot be detected. Read the draft before publishing it, especially for projects you did not write.
- **Small-model quality**: `gemma4:e4b` writes solid first drafts, but phrasing varies between runs and it can miss details in files outside the 30k-character budget. Always review the draft before publishing. A larger model (`MODEL_NAME=gemma4:12b`) may give richer drafts at the cost of speed.
- **Occasional empty reply**: Rarely, the model returns an empty or malformed reply. The CLI then prints a message and exits with code 1. Running again fixes it. The agent also asks LiteLLM to retry failed requests (`num_retries=3`).
- **Thinking mode is disabled on purpose**: With Gemma's thinking enabled, a test run invented files and tool results that did not exist, so the agent sets `reasoning_effort="none"`.
- **Ollama context on macOS (MLX runner)**: The context size is fixed when the model first loads. If you ran `ollama run gemma4:e4b` before starting the agent, the model may be stuck at 4,096 tokens. Run `ollama stop gemma4:e4b` once and the agent will load it with 32,768.
- **Docker on macOS is CPU-only** for the bundled Ollama. Use the fast path above.
- **Tested on**: macOS (Apple Silicon, OrbStack) with `gemma4:e4b`, both as local Python and as the agent container using the Mac's Ollama, on `pypa/sampleproject`, ADK's own source tree and this project. The fully bundled stack (Ollama inside Docker, automatic model pull) was verified end to end with a small model; running `gemma4:e4b` on CPU inside Docker has not been benchmarked. Linux and Windows hosts are untested.
- **Single folder per run**: The project folder is fixed by `PROJECT_DIR` when the agent starts. Restart to document a different project.

---

## Security & Privacy Considerations

The project being documented is treated as **untrusted input**: it may come from the internet and be written to attack whoever runs the drafter. All checks live in [`readme_drafter/guardrails.py`](readme_drafter/guardrails.py) and are covered by `tests/test_security.py`.

| Threat | Guardrail |
| :--- | :--- |
| A file in the project is a symlink to `~/.aws/credentials`, `~/.ssh/id_rsa` or another private file (git creates symlinks when cloning) | Every path is resolved first, and anything outside `PROJECT_DIR` is refused. This also applies to manifests and the license file. |
| Secrets inside the project: `.env`, keys, `.git/config` with a password in the remote URL | Never opened: `.env*` (except `.env.example`/`.sample`/`.template`), `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.jks`, `*.kdbx`, `id_rsa*`/`id_ed25519*`/`id_ecdsa*`, `credentials*`, `service-account*.json`, `.npmrc`, `.pypirc`, `.netrc`, `.pgpass`, `.git-credentials`, `.htpasswd`, `*.tfstate`, `*.tfvars`, `kubeconfig`, `*.ovpn`, and anything under `.git`, `.ssh`, `.aws`, `.gnupg`, `.kube`, `.docker`, `node_modules`, `.venv` and build folders. |
| Hard-coded secrets in code and config | Redacted before the model sees them and again in the output: private key blocks, OpenAI/Anthropic/Google/GitHub/AWS/Slack/JWT tokens, passwords in URLs (`postgres://user:[REDACTED]@host`), quoted values of keys named like `password`/`secret`/`token`/`api_key`, and unquoted values in config files. Variable names and `${VAR}` references are kept. Only names, never values, are taken from `.env.example`. |
| Prompt injection: project text tells the model to add `curl ... \| bash`, a tracking image or a phishing link | Project data is wrapped in `<<<PROJECT_DATA` markers and labelled untrusted in the instructions. Because a small model still obeys such text, every README is then reviewed in code: download-and-run commands (`curl/wget \| sh`, `bash <(curl ...)`, PowerShell `iex`, `base64 -d \| sh`) and destructive ones (`rm -rf ~`, `mkfs`, `dd of=/dev/...`) are removed. Images and links whose host does not appear in the project are removed. A `[!WARNING]` note at the top lists every change, with commands and addresses defanged (`hxxps`, `¦`) so they cannot be pasted and run. |
| Text that makes the agent loop or read endlessly | At most 4 tool calls and 6 model calls per request. At most 5,000 files are walked and 30,000 characters of file content are sent. Malformed manifests are reported as errors instead of crashing the run. |
| Running it on your home folder or `/` by mistake | Refused, as is any folder containing `.ssh`, `.aws` or `.gnupg` (it looks like a home folder, including under Docker). |
| Someone else on the same Wi-Fi opening the unauthenticated dev UI | Docker publishes port 8000 on `127.0.0.1` only. `adk web` run locally also binds to `127.0.0.1` by default. |
| A compromised agent container | Runs as an unprivileged user with a read-only root filesystem, all Linux capabilities dropped and `no-new-privileges`. The project is mounted read-only. The agent has no tool that runs code or commands, and it can only write `output/README.draft.md`. |

- **Data Privacy**: Nothing leaves your machine. The model runs in Ollama locally. LiteLLM's default download of a model price list from GitHub at start-up is turned off (`LITELLM_LOCAL_MODEL_COST_MAP=True`), verified by starting the container with networking disabled.
- **Local chat history**: `adk web` stores chat sessions, including the inspected file contents, in `readme_drafter/.adk/session.db`. It is git-ignored and excluded from the Docker image, and under Docker it is kept in memory only. Delete it to clear the history.
- **Remaining risks**:
  - Injected misinformation in plain words is not detected; review the draft.
  - Redaction is pattern-based, so a secret in an unusual format (for example, a password written in prose) can slip through.
  - Hard links cannot be told apart from normal files. Git never creates them, but archives can.
  - The dev UI has no login, so do not leave it running on a shared machine.

---

## Future Improvements

- [ ] Let the user pick a sub-folder from the chat instead of restarting with a new `PROJECT_DIR`.
- [ ] Map-reduce summarisation for very large repositories, so files outside the budget are summarised instead of skipped.
- [ ] Option to fill in an existing README's TODOs instead of drafting from scratch.

---

## License

This project is contributed under the repository's open-source license (MIT).
