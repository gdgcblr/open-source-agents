# MergeMesh — Google ADK Agent Architecture (Local-First Runtime)

## Role of AI vs. Deterministic Code

MergeMesh strictly separates **deterministic ground truth** from **optional local model-assisted interpretation**:

1. **Deterministic Tools (`agents/tools.py`) — Ground Truth Authority**
   - `load_scenario(scenario_id)`: Loads and validates local scenario metadata.
   - `inspect_contracts(scenario_id)`: Extracts and diffs before/after REST JSON contracts (`analysis/contract_extractor.py`).
   - `inspect_consumer_access(scenario_id)`: Scans consumer Python AST for dictionary accesses (`analysis/consumer_usage.py`).
   - `execute_allowlisted_test(scenario_id, test_kind)`: Runs allow-listed `pytest` checks in a bounded subprocess (`execution/runner.py`).
   - `assemble_evidence(scenario_id)`: Correlates contract changes, consumer usage, and executed test results (`analysis/compatibility.py`).

2. **ADK Explainer Agent (`agents/factory.py`, `agents/workflow.py`) — Local-Only Runtime**
   - Uses `google.adk.agents.Agent` and `google.adk.runners.InMemoryRunner`.
   - **Local Mode (`MERGEMESH_AI_MODE=local`, Default):** Uses `google.adk.models.lite_llm.LiteLlm(model="ollama_chat/<OLLAMA_MODEL>")` to call local Gemma (`gemma3:4b`) via Ollama on `http://localhost:11434`. Only loopback URLs (`localhost` / `127.0.0.1` / `::1`) are contacted.
   - **Deterministic Mode (`MERGEMESH_AI_MODE=deterministic`):** Skips LLM invocation completely and generates structured ground-truth explanations directly from measured AST, contract diff, and `pytest` execution evidence.
   - **Zero External API Dependency:** Hosted external LLM providers are disabled in the runtime so no source code, diffs, fixtures, or prompts are transmitted externally and zero API keys or paid credits are required.
   - **Validation & Fallback:** Model outputs are validated against `AIExplanationSchema` (`agents/schemas.py`). If Ollama is offline, the model is not pulled, or validation fails, `workflow.py` preserves all deterministic findings and returns a clearly labelled deterministic fallback explanation (`status="FALLBACK"` or `"UNAVAILABLE"`).
