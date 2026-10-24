from fastapi.testclient import TestClient

from networking_agent.api import create_app
from networking_agent.config import load_config
from networking_agent.llm import LLM
from networking_agent.service import EventService

ADMIN = {"X-Admin-Token": "test-admin"}


def make_client():
    service = EventService(load_config("config/event.example.yaml"), LLM(mode="offline"))
    return TestClient(create_app(service, admin_token="test-admin"))


def join(client, nickname, about, contact=None):
    r = client.post("/api/join", json={"nickname": nickname, "about": about, "contact": contact})
    assert r.status_code == 200, r.text
    return {"X-Attendee-Token": r.json()["token"]}, r.json()["me"]


def test_full_flow():
    client = make_client()
    people = [
        join(client, f"p{i}", "Developer building AI agents, looking for collaborators", contact=f"p{i}@example.com")
        for i in range(5)
    ]
    (h0, me0), (h1, me1) = people[0], people[1]

    assert client.get("/api/me/room", headers=h0).json() is None
    assert client.post("/api/me/room/meet", headers=h0).status_code == 409  # no room yet

    assert client.post("/api/admin/rounds").status_code == 422  # header missing
    assert client.post("/api/admin/rounds", headers={"X-Admin-Token": "nope"}).status_code == 403
    assert client.post("/api/admin/rounds", headers=ADMIN).json() == {"round": 1, "rooms": 1}

    room = client.get("/api/me/room", headers=h0).json()
    assert len(room["members"]) == 5
    assert "about" not in room["members"][0] and "contact" not in room["members"][0]
    assert room["votes_needed"] == 3

    for h, _ in people[:2]:
        assert client.post("/api/me/room/meet", headers=h).json()["meetup"] is None
    room = client.post("/api/me/room/meet", headers=people[2][0]).json()
    assert room["votes"] == 3 and room["meetup"]["spot_id"]

    assert client.post("/api/me/like", headers=h0, json={"to_id": me1["id"]}).json() == {"mutual": False}
    assert client.get("/api/me/connections", headers=h0).json() == []
    assert client.post("/api/me/like", headers=h1, json={"to_id": me0["id"]}).json() == {"mutual": True}
    assert client.get("/api/me/connections", headers=h0).json() == [{"nickname": "p1", "contact": "p1@example.com"}]


def test_cannot_connect_with_strangers():
    client = make_client()
    h0, _ = join(client, "a", "student")
    _, stranger = join(client, "b", "student")
    r = client.post("/api/me/like", headers=h0, json={"to_id": stranger["id"]})
    assert r.status_code == 400


def test_bad_token_is_rejected():
    client = make_client()
    assert client.get("/api/me", headers={"X-Attendee-Token": "forged"}).status_code == 401


def test_world_and_demo_endpoints():
    client = make_client()
    # Root serves the 2D virtual-world UI
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "world-canvas" in res_root.text

    # Seed synthetic bots, join a human, start a round, and simulate floor votes/likes
    h0, me0 = join(client, "chai-coder", "Backend developer into AI agents and RAG", contact="@chai")
    seed_res = client.post("/api/demo/seed", json={"count": 9, "use_llm": False}).json()
    assert seed_res["added"] == 9
    assert seed_res["attendees"] == 10

    round_res = client.post("/api/demo/round").json()
    assert round_res == {"round": 1, "rooms": 2}

    world = client.get("/api/world").json()
    assert world["round"] == 1
    assert len(world["attendees"]) == 10
    assert len(world["rooms"]) == 2
    assert len(world["spots"]) == 5

    # Human votes to meet; simulate lets bot roommates finish quorum and reciprocate likes
    room_before = client.post("/api/me/room/meet", headers=h0).json()
    assert room_before["i_voted"] is True

    sim_res = client.post("/api/demo/simulate", json={"meet_prob": 0.8, "like_prob": 1.0}).json()
    assert sim_res["meetups_this_round"] >= 1

    room_after = client.get("/api/me/room", headers=h0).json()
    assert room_after["meetup"] is not None

    assert client.post("/api/demo/reset").json() == {"ok": True}
    assert client.get("/api/world").json()["round"] == 0
    assert len(client.get("/api/world").json()["attendees"]) == 0
