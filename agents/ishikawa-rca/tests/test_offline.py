"""Offline tests: no API key or network needed."""

import json
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ishikawa import tools as t
from ishikawa.agent import build_root_agent
from ishikawa.render import fishbone_mermaid, to_markdown
from ishikawa.schema import CATEGORIES, RCAReport
from server import app


def ctx(**state):
    return SimpleNamespace(state=state)


@pytest.mark.parametrize("inc", [i["id"] for i in t.list_incidents()])
def test_fixtures_complete(inc):
    data = t.load_incident(inc)
    for key in ("alert", "deploys", "diffs", "logs", "metrics", "config_revisions", "dependencies", "traffic", "database"):
        assert key in data, f"{inc} missing {key}"
    for d in data["deploys"]:
        assert d["sha"] in data["diffs"], f"{inc}: no diff for {d['sha']}"


def test_unknown_incident_rejected():
    with pytest.raises(ValueError):
        t.load_incident("../../etc/passwd")


def test_tools_read_active_incident():
    c = ctx(incident_id="payments-5xx")
    assert t.get_alert(c)["service"] == "payments-api"
    assert "DB_POOL_MAX" in t.get_commit_diff("infra-8812", c)
    errors = t.search_logs("", c, severity="error")
    assert errors and all(line["severity"] == "ERROR" for line in errors)
    assert len(errors) < len(t.search_logs("", c))
    assert t.get_commit_diff("; rm -rf /", c) == "invalid sha"
    assert t.get_commit_diff("--help", c) == "invalid sha"


def test_live_git_mode(tmp_path):
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    git("init", "-q")
    (tmp_path / "app.py").write_text("x = 1\n")
    git("add", ".")
    git("-c", "user.name=t|x", "-c", "user.email=t@t", "commit", "-qm", "feat: add app @@ | edge")
    c = ctx(incident_id="checkout-latency", repo_path=str(tmp_path))
    deploys = t.list_recent_deploys(c)
    assert deploys[0]["message"] == "feat: add app @@ | edge" and deploys[0]["author"] == "t|x" and deploys[0]["files"] == ["app.py"]
    assert "x = 1" in t.get_commit_diff(deploys[0]["sha"], c)
    assert t.get_commit_diff("deadbeef", c).startswith("git error")  # unknown sha must not raise


def test_agent_graph_shape():
    root = build_root_agent("gemini-test-model")
    names = [a.name for a in root.sub_agents]
    assert names == ["triage", "fishbone", "skeptic", "scribe"]
    assert {a.output_key for a in root.sub_agents[1].sub_agents} == {f"bone_{c}" for c in CATEGORIES}


SAMPLE = RCAReport(
    incident_title="Checkout API p95 latency breach",
    effect="p95 latency 2430ms",
    root_cause="N+1 query added in a1f3c9e",
    culprit="a1f3c9e",
    causes=[
        {"category": "code", "description": "N+1 query", "evidence": ["db_queries 3 -> 58"], "verdict": "root_cause", "confidence": 0.95},
        {"category": "traffic", "description": "Marketing email \"spike\"", "evidence": ["+18% | same as last week"], "verdict": "refuted", "confidence": 0.1},
    ],
    five_whys=["a", "b", "c", "d", "e"],
    immediate_fix="git revert a1f3c9e",
    corrective_actions=["revert"],
    preventive_actions=["add query-count assertion in CI"],
)


def test_markdown_render():
    md = to_markdown(SAMPLE, 12.3)
    assert "```mermaid" in md and "🎯" in md and "12.3s" in md
    assert "\\|" in md  # pipes in evidence are escaped for the table
    assert '"spike"' not in fishbone_mermaid(SAMPLE)  # quotes would break Mermaid labels


def test_http_api():
    client = TestClient(app)
    assert client.get("/").status_code == 200
    ids = [i["id"] for i in client.get("/api/incidents").json()]
    assert "checkout-latency" in ids
    assert client.get("/api/incidents/nope").status_code == 404
    assert client.get("/api/investigate/nope").status_code == 404
    r = client.post("/api/markdown", content=json.dumps(SAMPLE.model_dump()), headers={"Content-Type": "application/json"})
    assert r.status_code == 200 and "RCA:" in r.text
