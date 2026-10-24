# RunReady — Cloud Run Deployment-Rescue Agent

> A safety-first agent that diagnoses why a Python/FastAPI app fails to start on Google Cloud Run, proposes the smallest justified fix, and applies it **only after explicit human approval** — then reports honest, verified status.

> **Part of the two-piece RunReady submission:** this agent plus its model-backed eval harness, [`tools/runready-eval`](../../tools/runready-eval). The agent is standalone; the eval scores its diagnosis quality.

---

## Quick Start (for reviewers)

From a clean clone, the safety proof needs **no API key**:

```bash
cd agents/runready-cloudrun-agent
make install   # venv + deps (agent + sample app)
make test      # 13 model-free safety tests — the core proof, no API key
make demo      # diagnose + fix the bundled broken app on a throwaway copy, no API key

# or, containerized (same deterministic result, no key):
docker build -t rr-agent . && docker run --rm rr-agent
```

`make demo` runs against a *copy* of `sample_app/`, so the committed broken fixture is never mutated. The sections below cover the interactive and Gemini-backed paths the quickstart deliberately skips.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: The most common Cloud Run failure for Python services is mundane but costly: the container starts, the server points at the wrong module, and the platform reports `Container failed to start` / `ModuleNotFoundError`. Diagnosing it means reading a startup log, the entrypoint config, and the actual app layout, then making one tiny, exact edit. Done carelessly — or by an over-eager LLM with file-write and shell access — the "fix" can touch the wrong line, leak a credential from a log, or claim success it never verified.
- **Intended Users**: Developers and operations/platform engineers deploying Python/FastAPI services to Cloud Run who want an assistant that is **useful but constrained** — one that explains its reasoning with evidence, never writes without approval, and never pretends an applied patch is a verified deployment.

### Key Features
- **Evidence-backed diagnosis**: deterministic checks establish whether the entrypoint's `module:attr` target actually resolves to a file, whether the server binds `0.0.0.0:$PORT`, and what the log's `ModuleNotFoundError` names — separating *what the evidence shows* from *hypothesis*.
- **Minimal, exact, approval-gated patches**: RunReady proposes the single smallest change (e.g. `uvicorn main:app` → `uvicorn src.api:app`), shows a unified diff, and writes **nothing** until a human types `approve`.
- **Honest verification**: after a patch is applied, it runs `py_compile` + an import check via fixed command templates and reports real status (`PASSED` / `FAILED` / `SKIPPED` / `NOT_RUN`). A patch that is `APPLIED` is never reported as `VERIFIED` unless the checks actually pass.
- **Security boundary in code, not prompt**: the LLM reasons; deterministic Python enforces workspace confinement, path/patch validation, secret redaction, bounded execution, and the patch lifecycle. There is **no generic shell tool**.
- **Proven by a model-free test suite**: a 12-row adversarial suite (prompt injection, path traversal, symlink escape, stale patch, approval bypass, …) runs with **no API key**.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+ (developed and tested on 3.14).
- **Agent Framework / Core Library**: Google Agent Development Kit (**ADK 2.x**, verified against `google-adk` 2.13.0).
- **Models**: Gemini 2.5 Flash via Google AI Studio (configurable via `GEMINI_MODEL`).
- **External APIs / Tools**: none required for the safety core. Gemini is used only for the optional human-readable diagnosis narrative and the `adk web` UI. No cloud mutation is ever performed.

---

## Architecture & Data Flow

The model chooses *which* read-only tool to call and how to explain the evidence. It can never widen what a tool is allowed to do: every consequential operation is a dedicated function with fixed command templates and validated arguments, and all enforcement lives in `runready/policy.py`.

```
user request + project_root + optional startup log
        │
        ▼
 [deterministic] scope validation (realpath + commonpath; reject traversal/symlink escape)
        │
        ▼
   ADK Agent (Gemini Flash)  ◄── instruction: use tools, cite evidence, propose minimal patch
        │  (model never writes files or runs shell)
        ▼
 read-only tools → diagnosis → propose patch → [deterministic] validate_patch (hash + exact snippet)
        │                                              │
        ▼                                        valid + in scope?
 structured evidence                              /          \
                                                no            yes
                                                │              ▼
                                           explain/reject   show diff → CLI approve / reject
                                                                │ approved (re-check file hash)
                                                                ▼
                                                     apply only the approved diff  → APPLIED
                                                                ▼
                                                     validate_project (py_compile + import) → VERIFIED / FAILED
                                                                ▼
                                                     honest status + suggested gcloud command (no mutation)
```

**Patch lifecycle** (enforced by a transition guard — no skipping, no reversing):
`PROPOSED → VALIDATED → AWAITING_APPROVAL → APPROVED → APPLIED → VERIFIED` (or `→ REJECTED`). `APPLIED ≠ VERIFIED`.

---

## Prerequisites

- Python 3.10+ and `pip`.
- (Optional) A Google AI Studio API key — only for the Gemini narrative and `adk web`. The deterministic diagnosis, patching, validation, and the entire test suite run **without** a key.
- The sample app's runtime deps (`fastapi`, `uvicorn`) if you want the import check to pass on the bundled demo.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/runready-cloudrun-agent
   ```

2. **Set up the virtual environment and install dependencies:**
   ```bash
   python -m venv .venv
   # Linux/macOS:
   source .venv/bin/activate
   # Windows:
   .venv\Scripts\activate

   pip install -r requirements.txt
   # For the bundled sample app's import check:
   pip install -r sample_app/requirements.txt
   ```

3. **(Optional) Configure environment variables** (only for the Gemini narrative / `adk web`):
   ```bash
   cp .env.example .env
   # then edit .env and set GOOGLE_API_KEY
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | Only for the Gemini narrative / `adk web` | *None* | Google AI Studio API key. The deterministic safety core runs without it. |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | `FALSE` | Use AI Studio (not Vertex AI) with the key above. |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Gemini model id for the narrative. |

Never publish real secrets here. The committed `.env.example` contains placeholders only; `.env` is git-ignored.

---

## How to Run

The bundled `sample_app/` is an **intentionally broken** FastAPI project: its startup command points at `main:app`, but the app actually lives at `src.api:app`, producing the `ModuleNotFoundError: No module named 'main'` in `sample_app/startup.log`.

```bash
# Deterministic safety path — no API key needed. Run on a COPY so the demo
# fixture stays broken for the next run:
cp -r sample_app /tmp/rr_demo
python main.py /tmp/rr_demo --log /tmp/rr_demo/startup.log

# Non-interactive (auto-approve) for a scripted demo:
python main.py /tmp/rr_demo --log /tmp/rr_demo/startup.log --yes

# Deterministic-only, skip the Gemini narrative entirely:
python main.py /tmp/rr_demo --log /tmp/rr_demo/startup.log --no-model

# Gemini-backed narrative (requires GOOGLE_API_KEY in your environment/.env):
python main.py /tmp/rr_demo --log /tmp/rr_demo/startup.log

# Web UI (requires a key):
adk web      # then pick the "runready" agent
```

### Running in Docker

```bash
docker build -t rr-agent .

# Default CMD: deterministic diagnose+fix on a copy of the bundled sample, no key.
docker run --rm rr-agent

# Against YOUR project — mount exactly one project root at /work:
docker run --rm -v /abs/path/to/your/project:/work rr-agent \
    python main.py /work --log /work/startup.log --no-model --yes

# Mount read-only to exercise the reject / no-write path:
docker run --rm -v /abs/path/to/your/project:/work:ro rr-agent \
    python main.py /work --log /work/startup.log --no-model

# Gemini narrative in-container (optional): pass the key as an env var.
docker run --rm -e GOOGLE_API_KEY=... -v /abs/path/to/your/project:/work rr-agent \
    python main.py /work --log /work/startup.log
```

> **Confinement caveat (container-relative):** RunReady confines every file operation to one project root via `realpath` + `os.path.commonpath`. Inside a container that boundary is evaluated against the **container** filesystem, so mount exactly one project root at `/work` and pass `/work` as `project_root`. The guarantees are otherwise unchanged: no cloud mutation is ever performed, and no file is written without an explicit `approve` (or `--yes`).

At the approval prompt, type `approve` to apply the patch or `reject` to leave every file untouched.

> **Note:** running directly against `sample_app` (instead of a copy) will apply the fix in place and leave the fixture non-broken. Copy it first, as above.

---

## Example Input & Output

Command:

```bash
python main.py /tmp/rr_demo --log /tmp/rr_demo/startup.log --no-model --yes
```

Output (captured verbatim from a real run; `--no-model` so no key is involved):

```
==== EVIDENCE (deterministic) ================================================
  entrypoint: main:app
  entrypoint_source: app.yaml
  module_resolves: False
  expected_module_path: src.api:app
  binds_all_interfaces: True
  honours_port: True
  log.missing_module: main
  log.classification: startup_configuration

==== PROPOSED FIX (deterministic, minimal) ===================================
  state: PROPOSED
  target: app.yaml
  rationale: Startup entrypoint references module 'main', which does not resolve to a file; the ASGI app is defined in 'src.api'.
  state: VALIDATED

==== DIFF ====================================================================
--- a/app.yaml
+++ b/app.yaml
@@ -4,4 +4,4 @@
 # application actually lives at "src.api:app". This mismatch is what causes the
 # ModuleNotFoundError seen in startup.log, and what RunReady diagnoses.
 runtime: python
-entrypoint: uvicorn main:app --host 0.0.0.0 --port $PORT
+entrypoint: uvicorn src.api:app --host 0.0.0.0 --port $PORT

  (--yes) auto-approving
  state: APPLIED (file written)

==== VALIDATION (py_compile + import) ========================================
  [PASSED] py_compile:src/api.py: exit=0
  [PASSED] import:src.api: exit=0

  state: VERIFIED

==== NEXT STEP (no cloud mutation performed) =================================
  suggested: gcloud run deploy my-service --source . --region us-central1 --allow-unauthenticated
    - Authenticated gcloud CLI (`gcloud auth login`) and a selected project.
    - Cloud Run and Cloud Build APIs enabled on the project.
    - A correct startup entrypoint (apply RunReady's patch first).
    - Billing enabled; RunReady does not create or modify any cloud resource.
```

Note the diff targets the real `entrypoint:` line — not the word `main:app` in the comment above it. RunReady anchors on the unique full server-command fragment and **refuses to auto-propose** if the anchor is not unique, rather than risk editing the wrong occurrence.

---

## How to Test

The adversarial safety suite is the heart of this project and runs with **no API key**:

```bash
source .venv/bin/activate
pip install -r requirements.txt
pip install -r sample_app/requirements.txt   # fastapi/uvicorn, for the import-check row
pytest tests/ -q
```

Expected: all tests pass. The suite covers the 12 negative-test rows:

| # | Scenario | Invariant proven |
|---|----------|------------------|
| 1 | Happy path | Deterministic checks find the real module mismatch |
| 2 | Prompt injection in README/log | Malicious text never grants access; `.env` stays refused |
| 3 | Path traversal (`../../etc/passwd`) | Rejected on resolved path, not string prefix |
| 4 | In-workspace symlink to outside file | Symlink escape rejected |
| 5 | Secrets in text | API keys / bearer tokens / passwords redacted |
| 6 | Invalid/malformed patch | Rejected fail-closed (missing snippet, no-op) |
| 7 | Approval bypass | `validate_patch` never writes; lifecycle forbids `PROPOSED→APPLIED` |
| 8 | Stale patch (file changed) | Hash mismatch → rejected |
| 9 | Out-of-allowlist write (`.pem`, `.env`) | Blocked; normal source file allowed |
| 10 | Validation failure (syntax error) | Reported honestly as `FAILED`, never "verified" |
| 11 | Bounded execution | Budgets fail-closed; subprocess timeout honored |
| 12 | No cloud credentials | Diagnostics still work fully offline |

Manual end-to-end check: run the command in **How to Run**, confirm the diff, type `reject`, and verify with `git status` (on your copy) that no file changed; then run again and `approve`.

---

## Known Limitations

Being honest about what this does **not** do is part of the design:

- **No real cloud deployment.** RunReady never calls Cloud Run, never creates or modifies IAM policies or secrets, never mutates any cloud resource. It emits a *suggested* `gcloud` command for you to run yourself.
- **Diagnoses are hypotheses, not guarantees.** "Fail-safe" here means explicit controls on known failure modes — not a proof of correctness. The evidence is real; the root-cause attribution is a reasoned hypothesis.
- **Secret redaction is best-effort pattern matching.** It masks common credential shapes (`*_KEY/TOKEN/SECRET/PASSWORD=…`, Google `AIza…` keys, bearer tokens, private-key blocks) but **cannot guarantee** every secret is caught. Protected files (`.env`, `*.pem`, `*.key`, `credentials.json`, `.git/`, caches, venvs) are refused outright rather than redacted.
- **Scope is narrow by design.** Python/FastAPI module-path and bind/port startup problems. It is not a general-purpose code fixer.
- **Automatic patch proposal is conservative.** If the fix target is not uniquely locatable in the config file, RunReady declines to auto-propose and asks a human to edit — it will not guess.
- **The bundled model narrative varies.** The Gemini text is for human readability; the deterministic output is the authoritative record and is what the tests pin.

---

## Security & Privacy Considerations

RunReady treats the LLM as an untrusted reasoner and puts every real guarantee in deterministic code (`runready/policy.py`), with no dependency on ADK or the model. See that module for the enforcement; the properties:

- **Secrets handling**: credentials load from a git-ignored `.env` (never committed; `.env.example` has placeholders only). RunReady never prints environment variable values. Protected paths are denied by default; other text is passed through best-effort redaction before it ever reaches the model or output.
- **Workspace confinement**: one explicit project root. Every read/write path is resolved with `realpath` and checked for containment via `os.path.commonpath` on the *resolved* paths (not a string prefix), with an explicit symlink-escape walk. The check is re-run immediately before each write to defend against a mid-session symlink swap.
- **Prompt-injection resistance**: file and log contents are treated as untrusted data. Instructions embedded in a README or log ("reveal `.env`", "skip approval") cannot change what the policy permits — the policy layer does not read instructions.
- **No arbitrary code/shell execution**: there is no generic `run_shell` tool. Validation uses fixed command templates (`python -m py_compile <validated path>`, `python -c "import …"`) with validated, in-workspace arguments and a subprocess timeout + output cap.
- **Approval gating & patch integrity**: no file is written without an explicit `approve`. A patch names its target, the expected original hash, and the exact snippet; it is rejected if the file changed since it was read, if the snippet is missing, or if it is a no-op. Only the first occurrence of the approved snippet is replaced.
- **Bounded execution**: hard ceilings on turns, tool calls, files inspected, total/one-file bytes, subprocess time, and output size — all fail-closed.
- **Honest status**: an applied patch is reported `APPLIED`; it only becomes `VERIFIED` if `py_compile` + import actually pass. Failures are reported as `FAILED`, never silently as success. Deployment is never performed, so RunReady says "ready to deploy", not "deployed".

---

## Future Improvements

- [ ] Support more startup failure classes (missing dependency in `requirements.txt`, wrong `$PORT` handling, Dockerfile `CMD` mismatch).
- [ ] Optional AST-based patching instead of exact-snippet replacement for `.py` targets.
- [ ] Richer structured JSON output alongside the human-readable report.
- [ ] Pluggable, auditable redaction rules.

---

## License

This project is contributed under the repository's open-source license.
