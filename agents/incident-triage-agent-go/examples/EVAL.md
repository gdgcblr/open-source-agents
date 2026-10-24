# Eval results

`./eval.sh` on the lab, local `qwen3:4b-instruct` via Ollama (32K context), Apple M4 Pro, 24 Oct 2026.
For each scenario the harness resets the lab, waits for alerts to clear, injects the fault, waits for the real
Prometheus alert, runs one investigation, and passes it only if the *Most likely root cause* section names the
right service **and** cause, and does not blame the always-on `exchange-rate refresh failed` noise.

| Scenario | True root cause | Agent's root cause (verbatim) | Result | Time | Tool calls |
| :--- | :--- | :--- | :---: | ---: | ---: |
| latency | payments slow (+1.5 s); checkout is only the victim | payments: p99 latency 9.9x baseline | PASS | 13.7 s | 4 |
| pool | checkout DB pool exhausted (503); fx-refresh errors are a red herring | checkout: db connection pool exhausted (max=10) (NEW in this window) | PASS | 14.3 s | 4 |
| bad-deploy | checkout v1.4.0 deploy crashes in `applyCoupon` | checkout: panic recovered: nil pointer dereference in applyCoupon | MISS | 16.2 s | 4 |
| leak | checkout leaks memory and is OOM-killed | checkout: memory_rss_mb 2.2x baseline | PASS | 10.3 s | 4 |

**Score: 3/4** (strict grader). The bad-deploy miss is partial: the report's evidence cites the
`v1.3.0 -> v1.4.0` deploy "shortly before the symptom" and its first next step is "roll back checkout to
v1.3.0", but the one-line root cause names the crash without its trigger, so the grader fails it.

Raw harness output: [`eval-output.txt`](eval-output.txt). Unit tests (`go test ./...`): 7 tests, 26 cases, all passing.
