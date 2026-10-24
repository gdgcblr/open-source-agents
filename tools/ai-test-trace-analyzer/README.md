# AI Test Trace Analyzer

A pytest plugin that records project-local Python calls, returns, and exceptions, writes a JSON report, and optionally asks a local Ollama model to analyze test failures.

## Install

```cmd
python -m venv .venv
.venv\\Scripts\\activate
python -m pip install -e .
```

Install Ollama separately and pull a model, for example:

```cmd
ollama pull qwen2.5:3b
set OLLAMA_MODEL=qwen2.5:3b
set OLLAMA_TIMEOUT=180
```

## Trace tests

```cmd
python -m pytest --trace-calls
```

Analyze failed tests:

```cmd
python -m pytest --trace-calls --trace-ai
```

Analyze both passing and failing tests:

```cmd
python -m pytest --trace-calls --trace-ai-all
```

The report defaults to `trace-report.json`. Override it with `--trace-output path.json`.

## Trace IDs

Every traced test receives a unique `trace_id`. That ID is present on the test record and every call/return/exception event for that test. Instrumented services can access the current ID using:

```python
from ai_test_trace_analyzer.tracing_context import get_trace_id

trace_id = get_trace_id()
```

For HTTP calls, forward it as `X-Trace-ID`. The same ID lets you correlate the test's trace with service logs and downstream error responses.

## Service A -> Service B failure demo

Install the optional demo dependencies:

```cmd
python -m pip install -e ".[demo]"
```

Run the deliberately failing distributed-service demo:

```cmd
python -m pytest examples/test_distributed_failure_demo.py --trace-calls --trace-ai -s
```

**This particular demo is expected to fail.** Service A calls Service B with the same `X-Trace-ID`. Service B returns HTTP 500 with an `InventoryDatabaseError`; Service A returns HTTP 502 and preserves Service B's error details. The test intentionally expects HTTP 200 so the failure and downstream response are captured for AI analysis.

The demo uses in-process ASGI transport so it is easy to run locally. For independently running processes, forward `X-Trace-ID` and instrument each service separately. This pytest tracer cannot directly inspect function calls in another process; the shared ID and propagated error/log data provide correlation.

## Scope and privacy

The tracer records project-local Python calls, source locations, exception types/messages, durations, thread IDs, and trace IDs. It does not record function arguments or local variable values. HTTP traffic is not automatically instrumented. Avoid adding secrets or sensitive payloads to trace metadata. AI diagnosis is a hypothesis based on the captured evidence, not a guarantee.
