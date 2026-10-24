from pathlib import Path
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import json
import sys
import xml.etree.ElementTree as ET

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app, DEMO_EVENT
from importer import read_xlsx
from matching import eligible, tags
from agent import gemini_search

SAMPLE = Path(__file__).resolve().parents[1] / "sample/form-responses.xlsx"

@pytest.fixture
def fixture(tmp_path):
    now = [1_800_000_000.0]
    app = create_app(tmp_path / "test.sqlite3", admin_key="test-organizer", demo=True, clock=lambda: now[0])
    with TestClient(app,base_url="http://localhost") as client:
        yield client, app.state.store, now

def auth(token="demo-P001"):
    return {"Authorization": "Bearer " + token}

def matches(client, token="demo-P001", event=DEMO_EVENT, **payload):
    return client.post("/api/matches", params={"event": event}, headers=auth(token), json=payload)

def modified_cell(address, value=None, formula=None):
    # Modify the fixture's XML in memory; no spreadsheet-authoring dependency is needed.
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    output = BytesIO()
    with ZipFile(SAMPLE) as source, ZipFile(output, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                root = ET.fromstring(data)
                cell = next(c for c in root.iter(ns + "c") if c.attrib.get("r") == address)
                for child in list(cell):
                    cell.remove(child)
                if formula:
                    cell.attrib.pop("t", None)
                    ET.SubElement(cell, ns + "f").text = formula
                else:
                    cell.set("t", "inlineStr")
                    ET.SubElement(ET.SubElement(cell, ns + "is"), ns + "t").text = value or ""
                data = ET.tostring(root)
            target.writestr(item, data)
    return output.getvalue()

def test_sample_consent_and_data():
    people, skipped = read_xlsx(SAMPLE.read_bytes())
    assert len(people) == 18 and skipped == 2
    assert people[0]["id"] == "P001"
    assert all("consent" not in p and "email" not in p for p in people)

@pytest.mark.parametrize("cell,value,expected", [
    ("A1", "unknown", "Missing columns"),
    ("A3", "P001", "duplicate attendee"),
    ("A3", "bad/id", "attendee ID"),
    ("B2", "", "name is empty"),
    ("A20", "P001", "duplicate attendee"),
])
def test_import_errors(cell, value, expected):
    with pytest.raises(ValueError, match=expected):
        read_xlsx(modified_cell(cell, value))

def test_formula_and_invalid_zip_rejected():
    with pytest.raises(ValueError, match="formulas"):
        read_xlsx(modified_cell("C2", formula='HYPERLINK("https://example.com")'))
    with pytest.raises(ValueError, match="readable"):
        read_xlsx(b"not a spreadsheet")
    with pytest.raises(ValueError, match="5 MB"):
        read_xlsx(b"x" * (5 * 1024 * 1024 + 1))

def test_reciprocal_matching_and_evidence(fixture):
    client, _, _ = fixture
    result = matches(client).json()
    first = result["matches"][0]
    assert first["id"] == "P002"
    assert first["helps_you"] == ["deployment", "flutter"]
    assert first["you_help"] == ["api", "python"]
    assert first["score"] > 0
    assert first["label"] == "Offers relevant skills"
    assert "token_hash" not in json.dumps(result)
    assert all(p["id"] not in {"P001", "P019", "P020"} for p in result["matches"])

def test_query_and_no_hallucinated_matches(fixture):
    client, _, _ = fixture
    assert matches(client, query="quantum spectroscopy").json()["matches"] == []
    result = matches(client, query="I need Docker").json()
    assert result["skills"] == ["docker"]
    assert [p["id"] for p in result["matches"]] == ["P003"]

def test_availability_and_expiry(fixture):
    client, _, now = fixture
    assert matches(client, active_only=True).json()["matches"] == []
    assert client.post("/api/checkin", params={"event":DEMO_EVENT}, headers=auth("demo-P002"), json={"spot":"Table B","minutes":15}).status_code == 200
    current = matches(client, active_only=True).json()["matches"]
    assert len(current) == 1 and current[0]["spot"] == "Table B"
    assert matches(client, window="after talks", active_only=True).json()["matches"] == []
    now[0] += 900
    assert matches(client, active_only=True).json()["matches"] == []
    assert matches(client).json()["matches"][0]["spot"] is None

def test_invalid_checkin_and_token(fixture):
    client, _, _ = fixture
    assert matches(client, token="P001").status_code == 401
    assert matches(client, event="Other event").status_code == 401
    for payload, code in [({"spot":"Unconfigured","minutes":15},400),({"spot":"Table A","minutes":0},422)]:
        assert client.post("/api/checkin", params={"event":DEMO_EVENT}, headers=auth(),json=payload).status_code == code

def test_met_and_reset(fixture):
    client, _, _ = fixture
    assert client.post("/api/met/P002",params={"event":DEMO_EVENT},headers=auth()).status_code == 200
    assert "P002" not in [p["id"] for p in matches(client).json()["matches"]]
    client.delete("/api/met",params={"event":DEMO_EVENT},headers=auth())
    assert matches(client).json()["matches"][0]["id"] == "P002"

def test_import_auth_reimport_and_privacy(fixture):
    client, store, _ = fixture
    kwargs = {"data":{"event":"Real Event","spots":"Desk, Table C"},"files":{"file":("responses.xlsx", SAMPLE.read_bytes())}}
    assert client.post("/api/import", **kwargs).status_code == 401
    imported = client.post("/api/import",headers=auth("test-organizer"),**kwargs)
    assert imported.status_code == 200
    credentials = imported.json()["credentials"]
    assert len(credentials) == 18
    token = credentials[0]["token"]
    assert matches(client,token=token,event="Real Event").status_code == 200
    assert matches(client,token=token,event=DEMO_EVENT).status_code == 401
    assert all(p["token_hash"] != token for p in store.people("Real Event"))
    kwargs["files"] = {"file":("responses.xlsx", modified_cell("H3", "No"))}
    result = client.post("/api/import",headers=auth("test-organizer"),**kwargs).json()
    assert result["imported"] == 17 and result["credentials"] == []
    assert matches(client,token=token,event="Real Event").status_code == 200
    assert all(p["id"] != "P002" for p in store.people("Real Event"))

def test_failed_import_is_atomic(fixture):
    client, store, _ = fixture
    response=client.post("/api/import",headers=auth("test-organizer"),data={"event":"Broken","spots":"A"},files={"file":("bad.xlsx",modified_cell("A3","P001"))})
    assert response.status_code == 400
    assert store.people("Broken") == []

def test_withdrawal_and_checkout(fixture):
    client, store, _ = fixture
    client.post("/api/checkin",params={"event":DEMO_EVENT},headers=auth(),json={"spot":"Table A"})
    client.delete("/api/checkin",params={"event":DEMO_EVENT},headers=auth())
    assert client.get("/api/me",params={"event":DEMO_EVENT},headers=auth()).json()["until_ts"] == 0
    client.delete("/api/me",params={"event":DEMO_EVENT},headers=auth())
    assert matches(client).status_code == 401
    assert not any(p["id"] == "P001" for p in store.people(DEMO_EVENT))
    profiles, _ = read_xlsx(SAMPLE.read_bytes())
    store.import_event(DEMO_EVENT,["Table A"],profiles,demo=True)
    assert matches(client).status_code == 401
    assert not any(p["id"] == "P001" for p in store.people(DEMO_EVENT))

def test_organizer_can_rotate_lost_token(fixture):
    client, _, _ = fixture
    url = "/api/admin/rotate/P001"
    assert client.post(url,params={"event":DEMO_EVENT}).status_code == 401
    result = client.post(url,params={"event":DEMO_EVENT},headers=auth("test-organizer"))
    assert result.status_code == 200
    assert matches(client).status_code == 401
    assert matches(client,token=result.json()["token"]).status_code == 200

def test_non_demo_and_headers(tmp_path):
    with TestClient(create_app(tmp_path/"real.db",admin_key="secret"),base_url="http://localhost") as client:
        assert client.get("/api/demo").status_code == 404
        response = client.get("/")
        assert response.status_code == 200 and "BuildBuddy" in response.text
        assert response.headers["Cache-Control"] == "no-store"
        assert client.get("/api/events",headers={"Origin":"https://evil.example"}).status_code == 403

def test_gemini_validated_and_fallback(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY","fake-test-key")
    monkeypatch.setenv("GEMINI_MODEL","test-model")
    calls=[]
    def fake(*args, **kwargs):
        calls.append(json.loads(json.dumps(kwargs["json"])))
        call={"name":"search_people","args":{"query":"mobile app"}} if len(calls)==1 else {"name":"finish","args":{}}
        return httpx.Response(200,request=httpx.Request("POST","https://example.com"),json={"candidates":[{"content":{"role":"model","parts":[{"functionCall":call}]}}]})
    monkeypatch.setattr(httpx,"post",fake)
    trace=gemini_search("build mobile screens",lambda query: 2)
    assert trace[0]["tool"]=="search_people" and trace[-1]["tool"]=="finish"
    assert calls[1]["contents"][-1]["parts"][0]["functionResponse"]["response"]=={"hits":2}
    def fail(*args, **kwargs):
        raise httpx.ReadTimeout("timeout")
    monkeypatch.setattr(httpx,"post",fail)
    with pytest.raises(httpx.ReadTimeout):
        gemini_search("Flutter",lambda query:2)

def test_no_shared_window_and_aliases():
    assert tags("JS, k8s, backend") == {"javascript","kubernetes","api"}
    me={"id":"a","offers":"python","needs":"flutter","window":"Lunch","interests":"AI"}
    candidate={"id":"b","name":"B","offers":"flutter","needs":"python","window":"Evening","interests":"AI","project":"Test","until_ts":0,"spot":"","checked_at":0}
    assert eligible(me,[candidate],"",set(),False,0)[0] == []
    candidate["window"]="Anytime"
    assert len(eligible(me,[candidate],"",set(),False,0)[0]) == 1

def test_two_hundred_profile_catalog(fixture):
    client, store, _ = fixture
    profiles, _ = read_xlsx(SAMPLE.read_bytes())
    expanded = [{**profiles[i % len(profiles)], "id":f"B{i:03}"} for i in range(200)]
    credentials, count = store.import_event("Large Sample",["Table A"],expanded)
    assert count == 200
    response = matches(client,event="Large Sample",token=credentials[0]["token"])
    assert response.status_code == 200 and len(response.json()["matches"]) == 3
