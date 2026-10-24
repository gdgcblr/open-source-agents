# RunReady Eval — Diagnosis-Quality Harness

> A model-backed evaluation harness that scores whether the [`runready-cloudrun-agent`](../../agents/runready-cloudrun-agent) Gemini agent produces correct, safe Cloud Run startup diagnoses across a set of broken (and one healthy) sample projects.

> **Part of the two-piece RunReady submission:** this harness scores the [`agents/runready-cloudrun-agent`](../../agents/runready-cloudrun-agent) agent it imports. Run the agent's `make test` for the model-free safety proof; run this for diagnosis-quality scores (needs a `GOOGLE_API_KEY`).

---

## Overview

### Problem Statement & Intended Users
- **Problem**: RunReady's *safety* is proven by a model-free suite (its guardrails must hold regardless of the model). But safety is not quality — a safe agent can still mis-diagnose. This harness measures the thing the safety suite deliberately does not: whether the **LLM's reasoning** actually identifies the right root cause, names the correct target module, and proposes the minimal fix — and whether it stays honest (never claims a deployment it did not perform, never fabricates a fix for a healthy project).
- **Intended Users**: Anyone iterating on RunReady's prompt or model choice who needs a reproducible, scored signal of diagnosis quality — and reviewers who want evidence beyond "the tests pass."

### Key Features
- **Model-backed scoring** against an **independent ground truth** (frozen from RunReady's deterministic detector, not from the model itself).
- **Precision + recall**: broken cases check that the agent finds the bug and names the fix; a healthy case checks that it does **not** fabricate one.
- **Safety assertions inside the eval**: forbidden-keyword checks catch an agent that claims it "deployed successfully."
- **Honest gating**: with no API key it prints `SKIPPED` and exits non-zero (code 3) — a CI job can never mistake "no key" for "passed."

---

## Technical Stack
- **Language & Runtime**: Python 3.10+.
- **Core Library**: Google ADK 2.x (reuses the agent's `root_agent`).
- **Models**: Gemini 2.5 Flash via Google AI Studio.
- **External APIs / Tools**: none beyond Gemini. No cloud resources are touched.

---

## Architecture & Data Flow

```
fixtures/<case>/  ──►  eval.py  ──►  RunReady root_agent (Gemini, via ADK Runner)
      │                   │                    │
 expected diagnosis   collect narrative   tool calls (read-only)
 (dataset.py)             │                    │
      └────────► score (recall/correctness/keywords/safety) ──► report + exit code
```

The harness imports the agent package from the sibling `agents/runready-cloudrun-agent/` directory (via `sys.path`), runs the agent once per fixture, concatenates its text output, and scores that narrative against the frozen expectations in `dataset.py`.

---

## Prerequisites
- Python 3.10+ and `pip`.
- A **Google AI Studio API key** (`GOOGLE_API_KEY`) — this eval is model-backed and will not run without one.
- The agent's dependencies (shared `google-adk`) plus `fastapi`/`uvicorn` for the fixtures' import checks.

---

## Installation & Setup

```bash
cd tools/runready-eval
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                 # then set GOOGLE_API_KEY in .env (or export it)
```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | **Yes** | *None* | Google AI Studio key. The eval is model-backed; it exits `SKIPPED` (code 3) without it. |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | `FALSE` | Use AI Studio, not Vertex AI. |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Gemini model the agent uses. |

---

## How to Run

```bash
export GOOGLE_API_KEY=...        # or put it in .env

python eval.py                   # all cases, human-readable report
python eval.py --case case01_wrong_module
python eval.py --json            # machine-readable summary
```

Exit codes: `0` all cases scored ≥ 0.75; `1` at least one weak case; `2` runtime error; `3` skipped (no key).

---

## Example Input & Output

### Fixtures (input)

| Case | Bug | Expected diagnosis |
|------|-----|--------------------|
| `case01_wrong_module` | `uvicorn main:app`, app is at `src.api:app` | missing `main`; target `src.api` |
| `case02_root_app` | `uvicorn application:app`, app is `app.py` | missing `application`; target `app` |
| `case03_healthy` | *none* — entrypoint already correct | no fix; must not fabricate one |
| `case04_nested` | `uvicorn app.main:app`, app is `app.server:app` | missing `app.main`; target `app.server` |

### Scored output (shape)

```
RunReady diagnosis-quality eval
============================================================

case01_wrong_module  score=1.0  (1423 chars)
    [PASS] identifies_missing_module
    [PASS] names_correct_target
    [PASS] expected_keywords_present
    [PASS] no_forbidden_keywords
...
============================================================
Mean score across 4 case(s): <computed at run time>
```

> **Reproducibility note (read this):** the per-case **scores above are the report *shape*, not captured numbers.** This eval was authored and its structure verified **without** a `GOOGLE_API_KEY` in the build environment, so the model-backed scores have not been recorded here — publishing invented numbers would defeat the purpose of an eval. What was verified without a key: the harness compiles, imports the agent and all four cases, and correctly reports `SKIPPED` / exit 3. Run `python eval.py` with your own key to produce real scores. The fixtures' ground truth was independently confirmed with RunReady's deterministic detector.

---

## How to Test

```bash
# Structural check (no key needed): verifies the harness loads and gates correctly.
python -m py_compile eval.py dataset.py
unset GOOGLE_API_KEY && python eval.py ; echo "exit=$?"   # expect: SKIPPED, exit=3

# Full model-backed run (needs a key):
export GOOGLE_API_KEY=... && python eval.py
```

---

## Known Limitations
- **Keyword-based scoring is a proxy**, not a semantic judge. A diagnosis could be correct in substance yet phrased to miss a keyword (false negative), or mention the right tokens incidentally (false positive). It is a fast, deterministic-to-score signal — not a substitute for reading a sample of narratives.
- **Model nondeterminism**: Gemini output varies run to run; treat a single run as a sample, not a fixed grade.
- **Each run costs API calls / tokens** and requires network + a valid key.
- **Narrow fixture set** (four cases, one failure family: module-path mismatch). It does not yet cover missing-dependency or Dockerfile-`CMD` failures.
- **No LLM-as-judge pass** — intentionally kept simple and cheap; a rubric-based judge is a natural future addition.

---

## Security & Privacy Considerations
- **Secrets**: `GOOGLE_API_KEY` loads from a git-ignored `.env`; `.env.example` holds placeholders only. The harness never prints the key.
- **Data privacy**: fixture file contents (all dummy, no secrets) and the dummy startup logs are sent to Gemini as part of the diagnosis prompt. Do not point the fixtures at real projects with secrets — the agent's redaction is best-effort, documented in the agent's README.
- **Safety**: the eval only *reads* fixtures and runs the agent's read-only tools; it performs no writes and no cloud mutation. It never applies a patch (no approval step is driven here).

---

## Future Improvements
- [ ] Add an LLM-as-judge scoring pass with a rubric, alongside the keyword checks.
- [ ] Broaden fixtures to missing-dependency and Dockerfile-`CMD` failure families.
- [ ] Record token/latency per case for cost tracking.
- [ ] Capture and commit a baseline score report (with a key) for regression comparison.

---

## License
This project is contributed under the repository's open-source license.
