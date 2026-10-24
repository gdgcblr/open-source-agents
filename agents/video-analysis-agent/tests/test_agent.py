import json

import pytest

from video_analysis_agent import analysis as analysis_mod
from video_analysis_agent import cli, llm, video
from video_analysis_agent.errors import AnalysisError, ConfigError, LLMError, VideoError
from video_analysis_agent.llm import LLMClient, extract_json
from video_analysis_agent.pipeline import Options, run
from video_analysis_agent.report import render_markdown
from video_analysis_agent.schemas import Analysis, Report, ReportMeta, Transcript, TranscriptSegment
from video_analysis_agent.validate import coerce_analysis, verify_analysis

SEGS = [
    (0, "Okay team, let's start with the launch date."),
    (5, "I think we should maybe move the launch to Friday."),
    (10, "Agreed, we are launching on March 14th. That's final."),
    (15, "Priya, can you update the pricing page?"),
    (20, "Sure, I will finish it by Wednesday."),
    (25, "Does anyone know what the budget for ads is?"),
    (30, "Mumble mumble garbled."),
]


def make_transcript(low_last=True):
    segs = [TranscriptSegment(start=s, end=s + 4, text=t) for s, t in SEGS]
    segs[-1].low_confidence = low_last
    return Transcript(language="en", duration=34, segments=segs, source="demo.mp4")


class FakeLLM(LLMClient):
    provider, model = "fake", "fake-1"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def complete_json(self, system, user):
        self.calls += 1
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, str) else json.dumps(r)


GOOD = {
    "summary": "Team fixed the launch date.",
    "key_points": [{"point": "Launch date set", "quote": "we are launching on March 14th", "timestamp": "00:00:99"}],
    "decisions": [{"decision": "Launch March 14", "quote": "Agreed, we are launching on March 14th. That's final."}],
    "proposals": [{"suggestion": "Move launch to Friday", "quote": "we should maybe move the launch to Friday"}],
    "action_items": [
        {"task": "Update pricing page", "owner": "Priya", "deadline": "Wednesday", "quote": "I will finish it by Wednesday"},
        {"task": "Write blog post", "owner": "Bob", "deadline": "tomorrow", "quote": "Priya, can you update the pricing page?"},
    ],
    "facts": [{"kind": "date", "value": "March 14th", "quote": "launching on March 14th"}],
    "open_questions": [{"question": "Ad budget?", "quote": "what the budget for ads is"}],
    "insights": [{"text": "Pricing page gates launch", "kind": "insight", "quote": "invented quote nowhere"}],
}


def test_verify_keeps_supported_drops_invented():
    bad = [{"decision": "Hire CEO", "quote": "we will hire a new CEO"}, {"decision": "no quote"}]
    parsed, w = coerce_analysis({**GOOD, "decisions": GOOD["decisions"] + bad})
    assert any("malformed" in x for x in w)
    result, warnings = verify_analysis(parsed, make_transcript())
    assert [d.decision for d in result.decisions] == ["Launch March 14"]
    assert any("unsupported decisions" in x for x in warnings)
    assert result.decisions[0].timestamp == "00:00:10"
    assert result.key_points[0].timestamp == "00:00:10"  # LLM timestamp overwritten
    assert [p.suggestion for p in result.proposals] == ["Move launch to Friday"]  # not a decision


def test_owner_and_deadline_must_be_in_transcript():
    parsed, _ = coerce_analysis(GOOD)
    result, warnings = verify_analysis(parsed, make_transcript())
    by_task = {a.task: a for a in result.action_items}
    assert by_task["Update pricing page"].owner == "Priya"
    assert by_task["Update pricing page"].deadline == "Wednesday"
    assert by_task["Write blog post"].owner is None  # Bob never mentioned
    assert by_task["Write blog post"].deadline is None
    assert any("Bob" in w for w in warnings)


def test_insight_with_bad_quote_kept_but_unsourced():
    parsed, _ = coerce_analysis(GOOD)
    result, _ = verify_analysis(parsed, make_transcript())
    assert result.insights[0].quote is None and result.insights[0].timestamp is None


def test_coerce_rejects_non_object():
    with pytest.raises(AnalysisError):
        coerce_analysis([1, 2])


def test_extract_json_tolerates_fences_and_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Here you go: {"a": 1} hope it helps') == {"a": 1}
    with pytest.raises(json.JSONDecodeError):
        extract_json("no json here")


def test_chunking_splits_long_transcripts_with_overlap():
    segs = [TranscriptSegment(start=i, end=i + 1, text="word " * 20) for i in range(50)]
    chunks = analysis_mod.chunk_segments(segs, 1000)
    assert len(chunks) > 3
    assert chunks[1][0] is chunks[0][-analysis_mod.OVERLAP_SEGMENTS]
    assert {id(s) for c in chunks for s in c} == {id(s) for s in segs}


def test_analyze_retries_invalid_json():
    fake = FakeLLM(["not json at all", GOOD])
    result, _ = analysis_mod.analyze(make_transcript(), fake)
    assert fake.calls == 2 and result.decisions


def test_analyze_multi_chunk_partial_failure_and_merge():
    text = "says we are launching on March 14th"
    segs = [TranscriptSegment(start=i * 5, end=i * 5 + 4, text=f"Line number {i} {text}") for i in range(40)]
    tr = Transcript(segments=segs, duration=200)

    def part(s):
        return {"summary": s, "decisions": [{"decision": "Launch", "quote": "we are launching on March 14th"}]}

    n = len(analysis_mod.chunk_segments(segs, 600))
    assert n >= 5
    # part 1 ok, part 2 LLM error, part 3 invalid JSON twice, rest ok, then merge call
    replies = [part("one"), LLMError("boom"), "bad", "bad"] + [part("x")] * (n - 3) + [{"summary": "merged"}]
    result, warnings = analysis_mod.analyze(tr, FakeLLM(replies), 600)
    assert result.summary == "merged"
    assert sum("could not be analyzed" in w for w in warnings) == 2


def test_pipeline_from_transcript_json_writes_all_outputs(tmp_path):
    tjson = tmp_path / "t.json"
    tjson.write_text(make_transcript().model_dump_json())
    run(tjson, FakeLLM([GOOD]), Options(out_dir=tmp_path / "out"))
    out = tmp_path / "out"
    for name in ("report.md", "report.json", "transcript.json", "transcript.txt"):
        assert (out / name).exists()
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "Decisions (confirmed)" in md and "not agreed" in md and "low speech-recognition confidence" in md
    assert "Priya" in md and "not stated" in md
    data = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert data["analysis"]["decisions"][0]["timestamp"] == "00:00:10"


def test_pipeline_llm_failure_keeps_transcript(tmp_path):
    tjson = tmp_path / "t.json"
    tjson.write_text(make_transcript().model_dump_json())
    with pytest.raises(LLMError, match="re-run"):
        run(tjson, FakeLLM([LLMError("down")]), Options(out_dir=tmp_path / "out"))
    assert (tmp_path / "out" / "transcript.json").exists()


def test_video_validation(tmp_path):
    with pytest.raises(VideoError, match="not found"):
        video.validate_input(tmp_path / "nope.mp4")
    bad = tmp_path / "x.txt"
    bad.write_text("hi")
    with pytest.raises(VideoError, match="Unsupported"):
        video.validate_input(bad)
    empty = tmp_path / "e.mp4"
    empty.write_bytes(b"")
    with pytest.raises(VideoError, match="empty"):
        video.validate_input(empty)


class Resp:
    def __init__(self, code, body=None):
        self.status_code, self.text, self._body = code, "x", body or {"error": {"message": "slow down"}}

    def json(self):
        return self._body


def test_post_retries_then_succeeds(monkeypatch):
    seq = iter([Resp(429), Resp(500), Resp(200, {"ok": 1})])
    monkeypatch.setattr(llm, "_sleep", lambda s: None)
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: next(seq))
    assert llm._post_json("u", {}, {}) == {"ok": 1}


def test_post_gives_up_and_fails_fast_on_auth(monkeypatch):
    monkeypatch.setattr(llm, "_sleep", lambda s: None)
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: Resp(429))
    with pytest.raises(LLMError, match="after 4 attempts"):
        llm._post_json("u", {}, {})
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: Resp(401))
    with pytest.raises(LLMError, match="Authentication"):
        llm._post_json("u", {}, {})


def test_provider_autodetect_and_missing_key(monkeypatch):
    for v in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER", "MODEL_NAME"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(llm, "_can_prompt", lambda: False)
    with pytest.raises(ConfigError, match="No LLM API key"):
        llm.build_client()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    client = llm.build_client()
    assert client.provider == "anthropic" and client.model == llm.DEFAULT_MODELS["anthropic"]


def test_cli_errors(capsys, tmp_path):
    assert cli.main([]) == 1
    assert cli.main([str(tmp_path / "missing.mp4")]) == 1
    assert "File not found" in capsys.readouterr().err


def test_markdown_empty_sections():
    r = Report(meta=ReportMeta(source="a.mp4", generated_at="now"), analysis=Analysis(), transcript=make_transcript(False))
    assert "No confirmed decisions found" in render_markdown(r)


def test_fuzzy_quote_timestamp_points_at_start_segment():
    from video_analysis_agent.validate import TranscriptIndex

    idx = TranscriptIndex(make_transcript().segments)
    # "fourteenth" is not in the transcript text ("14th"), so this takes the fuzzy path.
    assert idx.locate("we are launching on March fourteenth") == 2
