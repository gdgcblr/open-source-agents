
"""pytest plugin: trace project-local calls and write a JSON report."""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import pytest

from .tracer import CallTracer
from .tracing_context import set_trace_id, reset_trace_id


def pytest_addoption(parser):
    group = parser.getgroup("trace-calls", "AI Test Trace Analyzer")

    group.addoption(
        "--trace-calls",
        action="store_true",
        default=False,
        help="Trace project-local Python calls during each test.",
    )
    group.addoption(
        "--trace-output",
        default="trace-report.json",
        metavar="PATH",
        help="Path for the JSON trace report.",
    )
    group.addoption(
        "--trace-max-events",
        type=int,
        default=20_000,
        help="Maximum number of trace events per test.",
    )
    group.addoption(
        "--trace-ai",
        action="store_true",
        default=False,
        help="Analyze failed tests using the configured AI analyzer.",
    )
    group.addoption(
        "--trace-ai-all",
        action="store_true",
        default=False,
        help="Analyze both passed and failed tests using AI.",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    config._ai_trace_records = {}
    config._ai_trace_current = {}


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_call(item):
    if not item.config.getoption("--trace-calls"):
        yield
        return

    max_events = item.config.getoption("--trace-max-events")
    if max_events < 1:
        raise pytest.UsageError("--trace-max-events must be >= 1")

    trace_id = uuid.uuid4().hex
    context_token = set_trace_id(trace_id)
    tracer = CallTracer(
        project_root=Path.cwd(),
        max_events=max_events,
        trace_id=trace_id,
    )

    nodeid = item.nodeid
    item.config._ai_trace_current[nodeid] = tracer
    start = time.perf_counter()

    tracer.start()
    try:
        yield
    finally:
        tracer.stop()

        duration = time.perf_counter() - start
        item.config._ai_trace_records[nodeid] = {
            "nodeid": nodeid,
            "trace_id": trace_id,
            "outcome": "unknown",
            "duration_seconds": round(duration, 6),
            **tracer.result(),
        }

        item.config._ai_trace_current.pop(nodeid, None)
        reset_trace_id(context_token)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    if report.when != "call":
        return

    record = item.config._ai_trace_records.get(item.nodeid)
    if record is None:
        return

    record["outcome"] = report.outcome

    if report.failed:
        record["failure"] = str(report.longrepr)[:5000]


def pytest_sessionfinish(session, exitstatus):
    config = session.config

    if not config.getoption("--trace-calls"):
        return

    report_path = Path(config.getoption("--trace-output"))
    if not report_path.is_absolute():
        report_path = Path.cwd() / report_path

    records = list(config._ai_trace_records.values())
    ai_results = {}

    analyze_failed = config.getoption("--trace-ai")
    analyze_all = config.getoption("--trace-ai-all")

    if analyze_failed or analyze_all:
        from .ai_analyzer import analyze_test

        for record in records:
            if record.get("outcome") != "failed" and not analyze_all:
                continue

            try:
                ai_results[record["nodeid"]] = analyze_test(record)
            except Exception as exc:
                ai_results[record["nodeid"]] = {
                    "status": "error",
                    "error": str(exc),
                    "hint": (
                        "Check the AI analyzer configuration, endpoint, "
                        "model availability, and API credentials if used."
                    ),
                }

    report_data = {
        "schema_version": "1.1",
        "summary": {
            "tests_traced": len(records),
            "passed": sum(
                record.get("outcome") == "passed" for record in records
            ),
            "failed": sum(
                record.get("outcome") == "failed" for record in records
            ),
            "events": sum(
                len(record.get("events", [])) for record in records
            ),
            "truncated_tests": sum(
                record.get("truncated", False) for record in records
            ),
        },
        "tests": records,
        "ai_analysis": ai_results,
    }

    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        terminal = config.pluginmanager.get_plugin("terminalreporter")
        if terminal:
            terminal.write_sep(
                "-",
                f"AI Test Trace Analyzer: report written to {report_path}",
            )
            terminal.write_line(
                f"Traced {report_data['summary']['tests_traced']} tests; "
                f"{report_data['summary']['events']} events; "
                f"{report_data['summary']['truncated_tests']} tests truncated."
            )

            if ai_results:
                terminal.write_line(
                    f"AI analysis entries: {len(ai_results)}"
                )

    except OSError as exc:
        terminal = config.pluginmanager.get_plugin("terminalreporter")
        if terminal:
            terminal.write_line(
                f"Could not write trace report: {exc}",
                red=True,
            )
