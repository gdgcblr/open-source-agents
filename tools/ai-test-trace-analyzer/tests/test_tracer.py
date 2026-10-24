from ai_test_trace_analyzer.tracer import CallTracer



def test_event_limit_marks_truncated(tmp_path):
    source = tmp_path / "sample.py"
    source.write_text("def f():\n    return 1\n")
    namespace = {}
    exec(compile(source.read_text(), str(source), "exec"), namespace)
    tracer = CallTracer(project_root=tmp_path, max_events=1)
    tracer.start()
    try:
        namespace["f"]()
    finally:
        tracer.stop()
    assert tracer.result()["truncated"] is True
