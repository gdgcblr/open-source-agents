"""End-to-end ADK pipeline runs (offline) and Arbiter grounding of LLM findings."""

from __future__ import annotations

import asyncio
import json

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

import testkit
from mergewarden import agent as gk
from mergewarden import cli
from mergewarden.models import Severity, Submission, Verdict


def test_offline_pipeline_good(contrib, upstream_repo):
    contrib(testkit.good_agent())
    rep = cli.review(str(upstream_repo), use_llm=False, quiet=True)
    assert rep.verdict is Verdict.READY and rep.findings == []
    assert cli.EXIT[rep.verdict] == 0
    assert rep.score() == 100 and not rep.llm_used
    assert "weather-brief" in rep.review_markdown


def test_offline_pipeline_blocked(contrib, upstream_repo):
    files = testkit.good_agent()
    files["agents/weather-brief/config.py"] = f"KEY = '{testkit.fake_google_key()}'\n"
    files["CONTRIBUTING.md"] = "Everything goes.\n"
    del files["agents/weather-brief/requirements.txt"]
    contrib(files)
    rep = cli.review(str(upstream_repo), use_llm=False, quiet=True)
    checks = {f.check for f in rep.findings}
    assert {"secrets.leaked", "scope.outside-project", "structure.manifest"} <= checks
    assert rep.verdict is Verdict.BLOCKED and cli.EXIT[rep.verdict] == 2
    assert testkit.fake_google_key() not in rep.review_markdown


def test_offline_pipeline_changes_requested(contrib, upstream_repo):
    files = testkit.good_agent()
    del files["agents/weather-brief/requirements.txt"]
    contrib(files)
    rep = cli.review(str(upstream_repo), use_llm=False, quiet=True)
    assert rep.verdict is Verdict.CHANGES_REQUESTED and cli.EXIT[rep.verdict] == 1


def test_cli_main_exit_code(contrib, upstream_repo, capsys):
    files = testkit.good_agent()
    files["agents/weather-brief/.env"] = "WEATHER_API_KEY=abc\n"
    contrib(files, force=("agents/weather-brief/.env",))
    code = cli.main(["review", str(upstream_repo), "--no-llm", "-q"])
    assert code == 2
    assert ".env" in capsys.readouterr().out


# ---- Arbiter: LLM findings must be grounded -------------------------------------

EVIDENCE = (
    "README.md:\n# Weather Brief\nThe CLI fetches the forecast and prints a three-line brief.\n"
    "## Known Limitations\nNone.\n"
)


def _run_arbiter(tmp_path, state: dict):
    async def go():
        runner = InMemoryRunner(agent=gk.Arbiter(name="arbiter"), app_name="t")
        session = await runner.session_service.create_session(app_name="t", user_id="u", state=state)
        # Grounding only accepts quotes from the contributor's own files, so the
        # README text has to exist in the submission, not just in the prompt.
        proj = tmp_path / "agents" / "weather-brief"
        proj.mkdir(parents=True, exist_ok=True)
        (proj / "README.md").write_text(EVIDENCE.split("README.md:\n", 1)[1])
        sub = Submission(root=tmp_path, project_dir="agents/weather-brief", changed_files=[])
        gk._LIVE[session.id] = {"sub": sub, "sandbox": None}
        try:
            msg = types.Content(role="user", parts=[types.Part(text="go")])
            async for _ in runner.run_async(user_id="u", session_id=session.id, new_message=msg):
                pass
            return gk._LIVE[session.id]["report"]
        finally:
            gk._LIVE.pop(session.id, None)
    return asyncio.run(go())


def _lf(check, severity, evidence, criterion="Documentation"):
    return {"check": check, "severity": severity, "criterion": criterion, "evidence": evidence,
            "message": f"{check} problem in the README.", "file": "README.md", "fix": "Fix it."}


def test_arbiter_demotes_hallucinated_quote(tmp_path):
    review = {
        "findings": [
            _lf("vague-limitations", "major", "## Known Limitations\nNone."),
            _lf("invented", "major", "This agent stores every prompt in a public S3 bucket"),
        ],
        "strengths": ["Clear one-line summary"],
    }
    rep = _run_arbiter(tmp_path, {"findings": [], "evidence": EVIDENCE, "doc_review": review})
    by = {f.check: f for f in rep.findings}
    assert by["llm.vague-limitations"].severity is Severity.MAJOR
    assert by["llm.invented"].severity is Severity.INFO
    assert "unverified" in by["llm.invented"].message
    assert all(f.source == "llm" for f in rep.findings)
    assert rep.verdict is Verdict.CHANGES_REQUESTED and rep.llm_used


def test_arbiter_accepts_json_string_and_keeps_deterministic(tmp_path):
    det = {"check": "secrets.leaked", "severity": "blocker", "criterion": "Security & Privacy",
           "message": "Google API key committed.", "file": "x.py", "line": 1, "fix": None,
           "rule": None, "source": "deterministic"}
    review = json.dumps({"findings": [_lf("empty-quote", "minor", "")], "strengths": []})
    rep = _run_arbiter(tmp_path, {"findings": [det], "evidence": EVIDENCE, "policy_review": review})
    by = {f.check: f for f in rep.findings}
    assert by["secrets.leaked"].severity is Severity.BLOCKER  # LLM can't remove it
    assert by["llm.empty-quote"].severity is Severity.INFO  # no quote = ungrounded
    assert rep.verdict is Verdict.BLOCKED


def test_arbiter_llm_cannot_produce_blocker_from_schema_values(tmp_path):
    review = {"findings": [_lf(c, s, "## Known Limitations\nNone.") for c, s in
                           [("a", "major"), ("b", "minor"), ("c", "info")]], "strengths": []}
    rep = _run_arbiter(tmp_path, {"findings": [], "evidence": EVIDENCE, "doc_review": review})
    assert max(f.severity.rank for f in rep.findings) < Severity.BLOCKER.rank
    assert rep.verdict is not Verdict.BLOCKED


def test_arbiter_clamps_out_of_schema_blocker(tmp_path):
    # The Arbiter also accepts raw JSON strings from state, which bypass the
    # LlmReview schema. A grounded "blocker" from the LLM must still be capped.
    review = json.dumps({"findings": [_lf("escalate", "blocker", "## Known Limitations\nNone.")],
                         "strengths": []})
    rep = _run_arbiter(tmp_path, {"findings": [], "evidence": EVIDENCE, "doc_review": review})
    assert [f.severity for f in rep.findings] == [Severity.MAJOR]  # grounded, but capped
    assert all(f.severity is not Severity.BLOCKER for f in rep.findings)
    assert rep.verdict is not Verdict.BLOCKED


def test_llm_finding_schema_forbids_blocker():
    with pytest.raises(Exception):
        gk.LlmFinding(check="x", severity="blocker", criterion="Documentation", message="m", evidence="e")
