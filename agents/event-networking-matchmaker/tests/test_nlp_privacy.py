from test_buildbuddy import fixture,auth,matches,SAMPLE
import json
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from agent import gemini_search,run_agent
from nlp import LocalEncoder

def test_renamed_demo_identity_and_matches(fixture):
    client,_,_=fixture
    demo=client.get('/api/demo').json()
    assert next(p for p in demo if p['id']=='P001')['name']=='Adarsh'
    me=client.get('/api/me',params={'event':'BuildBuddy Sample Event'},headers=auth()).json()
    assert me['name']=='Adarsh'
    result=matches(client,query='I want to start contributing to open source').json()
    assert {'P011','P012'}.issubset({p['id'] for p in result['matches']})

def test_original_open_source_regression(fixture):
    client,_,_=fixture
    data=matches(client,query="I want to know how I can start contributing to open source").json()
    ids=[p["id"] for p in data["matches"]]
    assert {"P011","P012"}.issubset(ids)
    assert data["mode"]=="Local lexical NLP"
    for p in data["matches"]:
        assert p["evidence"]
        assert all(e["text"]==p[e["field"]] for e in p["evidence"])

def test_paraphrase_expansion_and_project_retrieval(fixture):
    client,_,_=fixture
    cases=[("I need help with my first pull request",{"P011","P012"}),
           ("I want to put my app online",{"P003"}),
           ("I want to run AI offline",{"P006"}),
           ("I am working on a campus map",{"P016"})]
    for query,expected in cases:
        ids={p["id"] for p in matches(client,query=query).json()["matches"]}
        assert expected.intersection(ids),(query,ids)

def test_interest_is_not_claimed_expertise(fixture):
    client,_,_=fixture
    result=matches(client,query="open source").json()
    for p in result["matches"]:
        if p["label"]=="Shared-interest connection":
            assert not p["helps_you"]
            assert "not verified expertise" in p["caveat"]

def test_offered_only_filter(fixture):
    client,_,_=fixture
    result=matches(client,query="open source",offered_only=True).json()
    assert result["matches"]
    assert all(any(e["field"]=="offers" for e in p["evidence"]) for p in result["matches"])

def test_local_mode_makes_no_http_requests(fixture,monkeypatch):
    client,_,_=fixture
    def blocked(*a,**kw):
        raise AssertionError("Local mode must not call external providers")
    monkeypatch.setattr(httpx,"post",blocked)
    assert matches(client,query="open source").status_code==200

def test_gemini_discloses_no_profiles(fixture,monkeypatch):
    client,_,_=fixture
    monkeypatch.setenv("GEMINI_API_KEY","test-key")
    monkeypatch.setenv("GEMINI_MODEL","test-model")
    sent=[]
    def provider(*args,**kwargs):
        sent.append(json.loads(json.dumps(kwargs["json"])))
        call={"name":"search_people","args":{"query":"Git documentation open source"}} if len(sent)==1 else {"name":"finish","args":{}}
        return httpx.Response(200,request=httpx.Request("POST","https://example.com"),json={"candidates":[{"content":{"role":"model","parts":[{"functionCall":call}]}}]})
    monkeypatch.setattr(httpx,"post",provider)
    result=matches(client,query="open source",use_ai=True).json()
    assert "Gemini tool planner" in result["mode"]
    assert len(sent)==2
    serialized=json.dumps(sent)
    for forbidden in ("Priya","Farah","P011","Table B","token_hash","First contribution guide"):
        assert forbidden not in serialized

def test_unapproved_agent_tool_falls_back(fixture,monkeypatch):
    client,_,_=fixture
    monkeypatch.setenv("GEMINI_API_KEY","test-key")
    monkeypatch.setenv("GEMINI_MODEL","test-model")
    def provider(*a,**kw):
        return httpx.Response(200,request=httpx.Request("POST","https://example.com"),json={"candidates":[{"content":{"parts":[{"functionCall":{"name":"export_database","args":{}}}]}}]})
    monkeypatch.setattr(httpx,"post",provider)
    result=matches(client,query="open source",use_ai=True).json()
    assert result["warning"] and result["matches"]
    assert "Gemini tool planner" not in result["mode"]

def test_agent_boundaries(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY","test-key")
    monkeypatch.setenv("GEMINI_MODEL","test-model")
    count=[]
    def provider(*a,**kw):
        count.append(1)
        return httpx.Response(200,request=httpx.Request("POST","https://example.com"),json={"candidates":[{"content":{"parts":[{"functionCall":{"name":"search_people","args":{"query":"open source"}}}]}}]})
    monkeypatch.setattr(httpx,"post",provider)
    with pytest.raises(ValueError):
        gemini_search("open source",lambda q:0)
    assert len(count)==3

def test_delete_event_is_admin_only(fixture):
    client,store,_=fixture
    people=[{k:p[k] for k in ("id","name","offers","needs","interests","project","window")} for p in store.people("BuildBuddy Sample Event")]
    credentials,_=store.import_event("Private Event",["A"],people)
    assert client.delete("/api/admin/event",params={"event":"Private Event"},headers=auth(credentials[0]["token"])).status_code==401
    assert client.delete("/api/admin/event",params={"event":"Private Event"},headers=auth("test-organizer")).status_code==200
    assert store.people("Private Event")==[]
    assert matches(client,event="Private Event",token=credentials[0]["token"]).status_code==401

def test_missing_local_model_falls_back(tmp_path):
    encoder=LocalEncoder(str(tmp_path/"does-not-exist"))
    assert not encoder.available and encoder.error

def test_concurrent_requests_isolated(fixture):
    client,_,_=fixture
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda i:matches(client,token=f"demo-P{(i%18)+1:03}",query="open source"),range(24)))
    assert all(r.status_code==200 for r in results)
    for i,response in enumerate(results):
        assert all(p["id"]!=f"P{(i%18)+1:03}" for p in response.json()["matches"])

def test_large_chunked_body_and_untrusted_host(fixture):
    client,_,_=fixture
    def body():
        for _ in range(7):
            yield b"x"*(1024*1024)
    response=client.post("/api/import",content=body(),headers=auth("test-organizer"))
    assert response.status_code==413
    assert client.get("/api/events",headers={"Host":"attacker.example"}).status_code==400

def test_reassigned_id_revokes_old_credentials(fixture):
    client,store,_=fixture
    profiles=[{k:p[k] for k in ("id","name","offers","needs","interests","project","window")} for p in store.people("BuildBuddy Sample Event")]
    credentials,_=store.import_event("Reassigned",["A"],profiles)
    old=credentials[0]["token"]
    profiles[0]["name"]="Different attendee"
    new,_=store.import_event("Reassigned",["A"],profiles)
    assert len(new)==1
    assert matches(client,event="Reassigned",token=old).status_code==401
    assert matches(client,event="Reassigned",token=new[0]["token"]).status_code==200

def test_blank_goal_never_sends_stored_profile_to_cloud(fixture,monkeypatch):
    client,_,_=fixture
    def blocked(*a,**kw):
        raise AssertionError("Stored needs must not be sent to Gemini")
    monkeypatch.setattr(httpx,"post",blocked)
    result=matches(client,query="",use_ai=True).json()
    assert result["matches"] and "typed goal" in result["warning"]

def test_hosted_origin_behind_https_proxy(fixture,monkeypatch):
    client,_,_=fixture
    monkeypatch.setenv("BUILDBUDDY_PUBLIC_URL","https://demo.example")
    assert client.get("/api/config",headers={"Origin":"https://demo.example"}).status_code==200
    assert client.get("/api/config",headers={"Origin":"https://evil.example"}).status_code==403

def test_semantic_runtime_failure_falls_back(fixture):
    client,_,_=fixture
    class BrokenModel:
        def embed(self,*args,**kwargs):
            raise RuntimeError("model unavailable")
    encoder=LocalEncoder()
    encoder.model=BrokenModel()
    client.app.state.encoder.model=encoder.model
    result=matches(client,query="open source").json()
    assert result["mode"]=="Local lexical NLP"
    assert result["warning"] and result["matches"]

def test_200_profile_catalog(fixture):
    client,store,_=fixture
    base=store.people("BuildBuddy Sample Event")
    profiles=[]
    for i in range(200):
        p={k:base[i%18][k] for k in ("id","name","offers","needs","interests","project","window")}
        p.update(id=f"E{i:03}",name=f"Fictional attendee {i}")
        profiles.append(p)
    credentials,count=store.import_event("200-profile synthetic test",["A"],profiles)
    assert count==200
    result=matches(client,event="200-profile synthetic test",token=credentials[0]["token"],query="open source").json()
    assert len(result["matches"])==3
    assert all(p["id"]!="E000" and p["evidence"] for p in result["matches"])
