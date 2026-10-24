# Design: services, failure handling, guardrails and evaluation

Everything marked **(unverified)** has not been exercised end to end on the target hardware/models.
Only `gemma3:1b` was installed during development; no number below was measured on `gemma3:4b/12b/27b`.

## 1. Services and communication

```
 user ──► CLI  (python -m secret_scanner scan)  ───────────────┐ in-process Python call
 user ──► ADK web UI / adk run ─► ADK Runner ─► root_agent ──┐   │
                                   (in-process, Python)      │   │
                                                             │   │
          root_agent ──► LiteLLM (ollama_chat/<model>) ──────┼───┼──► Ollama server ──► Gemma model
                          HTTP, chat + tool calls            │   │    localhost:11434
                                                             ▼   ▼    /api/chat (JSON-schema `format`)
          ADK tools: scan_path(), remediation_guide() ──► scanner library (in-process)
                                                             │
                 filesystem / git index (READ-ONLY) ──► detectors ─► redactor ─► triage client ─► policy ─► reporter
                                                                                      │ HTTP
                                                                                      └──► Ollama /api/tags, /api/chat
 ═══════════ trust boundary: nothing below leaves localhost; raw secrets exist only inside detectors/redactor ═══════
```

| Component | Runtime / process | Talks to | Protocol & payload | Port |
| :--- | :--- | :--- | :--- | :--- |
| CLI (`secret_scanner.cli`) | Python process | scanner library | direct function call `scan(...)`; exit code 0/1/2 | - |
| ADK web UI / `adk run` | `adk` process (FastAPI/uvicorn for web) | ADK Runner | browser to `adk web`: HTTP, local only | 8000 (default; 8765 etc. via `--port`) |
| ADK Runner + `root_agent` | same process as above | LiteLLM; tools; callbacks | in-process Python; ADK events | - |
| LiteLLM (`ollama_chat/` prefix) | in `adk` process | Ollama | HTTP `POST /api/chat` with chat messages + tool schemas; `OLLAMA_API_BASE` | 11434 |
| ADK tools `scan_path`, `remediation_guide` | in `adk` process | scanner library | plain Python calls; return redacted dicts | - |
| Scanner library: detectors -> redactor -> triage client -> policy -> reporter | in-process | filesystem, git, Ollama | see below | - |
| Triage client (`secret_scanner.llm`) | in-process (httpx) | Ollama | `GET /api/tags` (health + model present); `POST /api/chat`, `stream:false`, `options.temperature:0`, `format:<JSON schema>` | 11434 |
| Ollama + Gemma | separate local process | - | JSON reply `{verdict, confidence, reason, remediation}` | 11434 |
| Filesystem / git | OS | detectors | read-only: `os.walk`, file reads, `git diff --cached`, `git show :path` | - |

Payloads:
- **Into the LLM** (per candidate, never raw): trusted metadata (rule, kind, known-format flag, test-path flag, redacted value such as `sk_live_51H****(39 chars, base64-like)`, placeholder-vocabulary hints) plus a **fenced** block `<<<BEGIN_UNTRUSTED_CODE ... END_UNTRUSTED_CODE>>>` holding the file:line and +/-2 redacted context lines.
- **Out of the LLM**: `{"verdict": "real|placeholder|test_fixture|false_positive", "confidence": 0..1, "reason": str, "remediation": str}`; validated/repaired locally, then masked.
- **ADK tool results**: redacted findings only (file, line, rule, kind, severity, verdict, confidence, reason, redacted_value).

Trust boundaries:
- Nothing leaves localhost by design: `OLLAMA_HOST` defaults to localhost. If a user points it at a remote host, redacted snippets and file paths go there.
- Raw secret values exist only inside `detectors.find_matches` (transient) and are converted to redacted form before a `Candidate` is built; the LLM and ADK layers never receive them.
- The ADK chat model sees the user's messages and tool results. A `before_model_callback` blocks raw-looking secrets in the newest message; tool results are already redacted.

## 2. Failure modes (principle: FAIL CLOSED)

Any LLM or infrastructure failure must never reduce the number of reported findings. The exit code is `1` if any non-dismissed or `unverified` finding exists, `2` if nothing was found but the scan was incomplete (unreadable files) or the environment is unusable with `--require-llm`, else `0`.

| Failure | Detection | Behaviour | Test |
| :--- | :--- | :--- | :--- |
| Ollama not running | `GET /api/tags` connect error in `OllamaClient.check()` | auto-fallback to deterministic mode, visible `WARNING` in report + stderr, all matches `unverified`; `--require-llm` makes it exit 2 instead | `test_failure_modes.py::test_ollama_down_falls_back_with_warning_and_keeps_findings`, `::test_require_llm_raises`, `test_files_and_cli.py::test_cli_ollama_down_falls_back_loudly`, `::test_cli_require_llm_is_strict` |
| Model not pulled | model absent from `/api/tags` | same fallback; warning names `ollama pull <model>` | `test_failure_modes.py::test_model_not_pulled_falls_back` |
| Ollama dies mid-run | `OllamaUnavailable` during triage | current + remaining candidates `unverified`, warning added | `test_failure_modes.py::test_llm_dies_midrun_remaining_unverified` |
| Timeout | httpx timeout (`OLLAMA_TIMEOUT`, default 180 s) | up to `max_retries` (2) retries with exponential backoff (0.5 s, 1 s, cap 8 s), then `unverified` | `::test_timeout_retries_with_backoff_then_unverified`, `::test_timeout_then_success` |
| Malformed / schema-violating JSON | `parse_triage_json` | local repair (fences, trailing commas, aliases, `85%`), else re-ask with a repair message (bounded), else `unverified` and the finding is KEPT | `test_llm.py::test_parse_*`, `test_llm.py::test_request_shape_and_retry_on_malformed`, `test_failure_modes.py::test_malformed_json_keeps_finding_unverified` |
| Hallucinated verdict / low confidence | invalid enum -> malformed path; dismissal below threshold (0.6, or 0.85 for known-format in test paths) | kept as `uncertain` with "NEEDS HUMAN REVIEW" | `::test_hallucinated_verdict_or_low_confidence_needs_review`, `test_safety_policy.py` |
| Unexpected exception in triage | catch-all around the LLM call | `unverified` | `::test_unexpected_exception_in_triage_fails_closed` |
| Binary / huge / lockfile / symlink | NUL byte, >1 MB, name, `is_symlink` | skipped and counted in the report (`Skipped: binary=.. too_large=..`) | `::test_skips_are_counted_in_report`, `test_files_and_cli.py::test_skip_rules` |
| Unreadable file / parser crash on one file | `OSError` / exception per file | counted in `errors`, scan continues, warning "INCOMPLETE", exit 2 if nothing else was found | `::test_unreadable_file_makes_scan_incomplete_nonzero`, `::test_one_bad_file_does_not_abort_scan` |
| Too many candidates | `max_llm_candidates` (default 200, `--max-llm-candidates`) | generic findings sent to the LLM first; the rest `unverified`; truncation warning. **Batching of several candidates per request is NOT implemented**: requests are sequential. | `::test_candidate_cap_reports_truncation` |
| Partial run crash | per-file and per-candidate isolation | everything processed so far is reported; the incomplete flag drives exit 2 | `::test_one_bad_file_does_not_abort_scan`, `::test_exit_code_matrix` |
| A hard crash of the Python process (SIGKILL, power loss) | - | **not handled**: no partial report is written (unverified). | - |

## 3. Guardrails

| # | Guardrail | Where | Test |
| :--- | :--- | :--- | :--- |
| a | Input redaction before any LLM call | `scanner.scan_text` builds only redacted candidates/context; `redaction.redact_line` also hides long opaque tokens | `test_redaction.py`, `test_no_leak.py::test_prompts_logs_reports_are_clean` |
| b | Output masking on every sink | `guardrails.mask_text/mask_obj` on LLM text, Markdown, JSON, logs (`safe_logger`), ADK tool results and model replies (`after_model_callback`) | `test_guardrails.py::test_mask_*`, `::test_llm_text_is_masked_in_findings`, `::test_log_masking`, `eval/test_agent_smoke.py::test_after_model_callback_masks_output` |
| c | LLM cannot dismiss known-format findings outside test paths | `triage.decide` | `test_safety_policy.py` |
| d | Read-only; path confinement | no write/delete/exec/network code in the library (static test); `confine()` resolves symlinks and rejects paths outside `SECRET_SCANNER_ROOT` when it is set (default: unset, any local path; read-only and masked either way); symlinked files are not followed | `test_guardrails.py::test_scanner_tools_are_read_only`, `::test_confine_*`, `::test_symlink_files_are_not_followed`, `eval/test_agent_smoke.py::test_scan_path_rejects_outside_root` |
| e | Prompt-injection resistance | untrusted fence + system rule; injection phrases near a finding set `injection_suspected` and block any dismissal; the fence tokens are stripped from file content | `test_injection.py` (4 phrases x 3 finding types with a worst-case "obedient" mock model) |
| f | ADK callbacks (`before_model_callback`, `before_tool_callback`, `after_model_callback`; signatures checked against google-adk 2.13.0) | `secret_scanner_agent/agent.py` | `eval/test_agent_smoke.py::test_before_model_callback_blocks_raw_secret`, `::test_before_tool_callback_blocks_secret_args_and_outside_paths` |
| g | Agent instruction forbids asking for or echoing secrets | `INSTRUCTION` | `eval/test_agent_smoke.py::test_agent_wiring`; behaviour with a real model is **(unverified)** |

Known gaps: the injection heuristic is regex-based (paraphrased attacks evade it, though known-format findings remain protected and the fenced prompt still applies); a model that obeys an undetected injection can still dismiss a *generic* finding; the model can still see a secret no rule recognises if it sits in a context line.

## 4. Evaluation

| What | How to run | Notes |
| :--- | :--- | :--- |
| Unit tests | `python -m pytest -q` | Ollama mocked; includes redaction, safety rule, failure modes, guardrails, injection |
| Benchmark | `python benchmark/run_benchmark.py --models gemma3:4b,gemma3:12b` | Runtime fixture: 16 planted + 3 injection-adjacent planted secrets, 15 decoys |
| Prompt-injection set | `pytest tests/test_injection.py` (mocked, deterministic) and `python benchmark/run_benchmark.py --injection-only --models <m>` (real model) | Primary safety metric: dismissed real secrets must be 0 |
| ADK eval | `adk eval secret_scanner_agent eval/secret_scanner.evalset.json --config_file_path eval/test_config.json --print_detailed_results` (project root; needs `google-adk[eval]`, Ollama and a **tool-calling** chat model) | 5 cases: scan a dir, remediation, refuse to reveal a secret, missing path, injection. (Root confinement is opt-in via SECRET_SCANNER_ROOT and covered by unit tests.) Tool-trajectory metric only (no LLM judge); results depend on the chat model. |
| Live agent smoke | `OLLAMA_AGENT_MODEL=<tool-model> RUN_LIVE_AGENT_TESTS=1 pytest eval/test_agent_smoke.py -m live -s` | |

Benchmark metrics per config: precision, recall, false positives and FP rate, **dismissed-real-secret count (primary safety metric, must be 0)**, JSON-validity rate (`1 - invalid/requests`), average seconds per candidate, total time. Recall counts only reportable findings; a planted secret that was detected and then dismissed counts in `dismissed_real_secrets`, one never detected counts as missed.

### Evaluation results (TO BE FILLED AFTER REAL RUNS - no numbers invented)

| Config | Dismissed real (must be 0) | Precision | Recall | FP rate | JSON valid | s/candidate | Total s |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `--no-llm` | see `benchmark/results/` | | | | n/a | | |
| `gemma3:4b` | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| `gemma3:12b` | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

ADK eval pass rate with a tool-calling model: TBD. The ADK eval was executed once against `gemma3:1b`; all 6 cases failed because Ollama reports that model "does not support tools" (an environment limitation, not a measurement of the agent).
