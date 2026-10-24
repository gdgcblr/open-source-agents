import hashlib
from io import BytesIO
import time
import zipfile

import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from curator.faces import FaceMatcher
from curator.web import create_app

HEADERS = {"X-Curator-Request": "local"}


@pytest.fixture
def local(tmp_path):
    app = create_app(tmp_path / "event")
    with TestClient(app) as client:
        client.get("/")
        yield client, tmp_path / "event"


def upload(client, path, name=None, **data):
    return client.post(
        "/api/upload",
        headers=HEADERS,
        data={"photographer": "Test Photographer", "permission": "true", **data},
        files=[
            (
                "files",
                (name or path.name, path.read_bytes(), "application/octet-stream"),
            )
        ],
    )


def await_job(client):
    for _ in range(200):
        state = client.get("/api/state").json()
        if not state["job"]["running"]:
            return state
        time.sleep(0.01)
    raise AssertionError("Background curation did not finish")


def test_local_access_and_csrf(tmp_path):
    with TestClient(create_app(tmp_path / "event")) as client:
        assert client.get("/api/state").status_code == 403
        client.get("/")
        assert client.get("/api/state").status_code == 200
        assert client.post("/api/curate", json={}).status_code == 403
        assert (
            client.post(
                "/api/curate",
                headers={**HEADERS, "Origin": "https://evil.example"},
                json={},
            ).status_code
            == 403
        )
        assert (
            client.get("/api/state", headers={"Host": "evil.example"}).status_code
            == 400
        )


def test_upload_thumbnail_original_and_attribution_export(local, sample):
    client, folder = local
    source = sample / "01-sharp.png"
    result = upload(client, source, "../../unsafe.png")
    assert result.status_code == 200, result.text
    photo_id = result.json()["added"][0]
    listing = client.get("/api/photos").json()["photos"]
    assert listing[0]["filename"] == "unsafe.png"
    assert listing[0]["photographer"] == "Test Photographer"
    thumb = client.get(f"/api/photos/{photo_id}/thumb")
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/webp"
    assert len(thumb.content) < 64 * 1024
    with Image.open(BytesIO(thumb.content)) as image:
        assert image.size == (640, 480)
    original = client.get(f"/api/photos/{photo_id}/original")
    assert (
        hashlib.sha256(original.content).digest()
        == hashlib.sha256(source.read_bytes()).digest()
    )
    exported = client.get(f"/api/photos/{photo_id}/export?watermark=TEST&metadata=true")
    assert exported.status_code == 200
    with Image.open(BytesIO(exported.content)) as image:
        assert image.getexif()[315] == "Test Photographer"
        assert image.size == (640, 480)
    stored = next((folder / "originals").iterdir())
    assert stored.read_bytes() == source.read_bytes()
    duplicate = upload(client, source, photographer="Someone Else")
    assert duplicate.json()["added"] == []
    assert (
        client.get("/api/photos").json()["photos"][0]["photographer"]
        == "Test Photographer"
    )


def test_upload_permission_and_corrupt_input(local, sample):
    client, _ = local
    assert (
        upload(client, sample / "01-sharp.png", permission="false").status_code == 400
    )
    response = client.post(
        "/api/upload",
        headers=HEADERS,
        data={"permission": "true", "photographer": "Test"},
        files=[
            ("files", ("bad.png", b"not a photo", "image/png")),
            ("files", ("bad.exe", b"text", "application/octet-stream")),
        ],
    )
    assert response.status_code == 200 and len(response.json()["errors"]) == 2
    assert client.get("/api/state").json()["count"] == 0


def test_background_review_all_images_and_zip(local, sample):
    client, _ = local
    for path in sorted(sample.iterdir()):
        assert upload(client, path).json()["added"]
    response = client.post(
        "/api/curate", headers=HEADERS, json={"provider": "mock", "top": 2}
    )
    assert response.status_code == 200
    state = await_job(client)
    assert not state["job"]["error"] and state["job"]["reviewed"] == 6
    assert state["picked"] == 2
    rows = client.get("/api/photos").json()["photos"]
    assert all(
        p["assessment"] for p in rows
    ), "Technical hints must not bypass AI review"
    picks = client.get("/api/photos?best=true").json()["photos"]
    archive = client.get("/api/picks.zip")
    assert archive.status_code == 200
    with zipfile.ZipFile(BytesIO(archive.content)) as zipped:
        assert len(zipped.namelist()) == 2
        assert {
            hashlib.sha256(zipped.read(name)).hexdigest() for name in zipped.namelist()
        } == {p["id"] for p in picks}
    client.post("/api/curate", headers=HEADERS, json={"provider": "mock", "top": 2})
    state = await_job(client)
    assert state["job"]["cache_hits"] == 6


def test_face_consent_results_and_clear_index(local, sample, monkeypatch):
    client, folder = local
    photo_id = upload(client, sample / "01-sharp.png").json()["added"][0]

    class Matcher:
        def __init__(self, folder):
            pass

        def encode(self, image):
            return [{"embedding": [1.0, 0.0], "box": [0.1, 0.1, 0.2, 0.2]}]

        similarity = staticmethod(FaceMatcher.similarity)

    monkeypatch.setattr("curator.web.FaceMatcher", Matcher)
    files = [
        ("files", ("selfie.png", (sample / "01-sharp.png").read_bytes(), "image/png"))
    ]
    assert client.post("/api/match", headers=HEADERS, files=files).status_code == 400
    result = client.post(
        "/api/match", headers=HEADERS, data={"consent": "true"}, files=files
    )
    assert result.status_code == 200, result.text
    assert result.json()["photos"][0]["id"] == photo_id
    assert result.json()["photos"][0]["similarity"] == 1
    assert not list(folder.rglob("*selfie*"))
    assert client.delete("/api/face-index", headers=HEADERS).json() == {"cleared": True}


def test_team_reference_can_have_multiple_faces(local, sample, monkeypatch):
    client, _ = local

    class Matcher:
        def __init__(self, folder):
            pass

        def encode(self, image):
            return [
                {"embedding": [1.0, 0.0], "box": [0.1, 0.1, 0.2, 0.2]},
                {"embedding": [0.0, 1.0], "box": [0.5, 0.1, 0.2, 0.2]},
            ]

        similarity = staticmethod(FaceMatcher.similarity)

    monkeypatch.setattr("curator.web.FaceMatcher", Matcher)
    files = [
        ("files", ("team.png", (sample / "01-sharp.png").read_bytes(), "image/png"))
    ]
    assert (
        client.post(
            "/api/match", headers=HEADERS, data={"consent": "true"}, files=files
        ).status_code
        == 400
    )
    result = client.post(
        "/api/match",
        headers=HEADERS,
        data={"consent": "true", "team": "true"},
        files=files,
    )
    assert result.status_code == 200 and result.json()["references"] == 2


def test_background_failure_keeps_previous_picks(local, sample, monkeypatch):
    client, _ = local
    upload(client, sample / "01-sharp.png")
    client.post("/api/curate", headers=HEADERS, json={"provider": "mock"})
    assert await_job(client)["picked"] == 1

    class Failed:
        name = "ollama"
        model = "gemma4:test"

        def __init__(self, model):
            pass

        def score(self, *args):
            raise RuntimeError("Local model unavailable; no cloud fallback.")

    monkeypatch.setattr("curator.web.OllamaProvider", Failed)
    client.post("/api/curate", headers=HEADERS, json={})
    state = await_job(client)
    assert state["picked"] == 1 and "unavailable" in state["job"]["error"]


def test_cosine_similarity_is_not_a_probability():
    assert FaceMatcher.similarity([1, 0], [1, 0]) == 1
    assert FaceMatcher.similarity([1, 0], [0, 1]) == 0
    assert FaceMatcher.similarity([1, 0], [-1, 0]) == -1
    assert FaceMatcher.similarity([0, 0], [1, 0]) == 0


def test_cancel_is_cooperative_and_gallery_stays_available(local, sample, monkeypatch):
    import threading

    client, _ = local
    for name in ("01-sharp.png", "04-scene.png"):
        upload(client, sample / name)
    entered, release = threading.Event(), threading.Event()

    class Slow:
        name = "test-slow"
        model = "slow"

        def __init__(self, model):
            pass

        def score(self, photos, style):
            entered.set()
            assert release.wait(5)
            return [
                dict(id=p.digest, score=8, reason="Test moment", caption="Test caption")
                for p in photos
            ], 0

    monkeypatch.setattr("curator.web.OllamaProvider", Slow)
    client.post("/api/curate", headers=HEADERS, json={})
    assert entered.wait(5)
    try:
        assert client.get("/api/photos").status_code == 200
        assert client.post("/api/curate", headers=HEADERS, json={}).status_code == 409
        assert upload(client, sample / "05-scene.png").status_code == 409
        assert client.post("/api/cancel", headers=HEADERS).status_code == 200
    finally:
        release.set()
    state = await_job(client)
    assert state["job"]["reviewed"] == 1
    assert "Stopped" in state["job"]["phase"]
    assert state["picked"] == 0


def test_paginated_gallery_does_not_return_originals(local, sample):
    client, _ = local
    for path in sample.iterdir():
        upload(client, path)
    first = client.get("/api/photos?limit=2").json()
    second = client.get("/api/photos?limit=2&offset=2").json()
    assert len(first["photos"]) == len(second["photos"]) == 2
    assert not {p["id"] for p in first["photos"]} & {p["id"] for p in second["photos"]}
    assert all("original" not in p and "faces" not in p for p in first["photos"])
    assert client.get("/api/photos?limit=10000").status_code == 400


def test_oversized_declaration_and_watermark_are_rejected(local, sample):
    client, _ = local
    assert (
        client.post(
            "/api/upload", headers={**HEADERS, "Content-Length": str(501 * 1024 * 1024)}
        ).status_code
        == 413
    )
    photo_id = upload(client, sample / "01-sharp.png").json()["added"][0]
    assert (
        client.get(
            f"/api/photos/{photo_id}/export", params={"watermark": "x" * 121}
        ).status_code
        == 400
    )


def test_event_directory_permissions(local):
    _, folder = local
    assert folder.stat().st_mode & 0o777 == 0o700


def test_metadata_is_actually_optional_and_blank_credit_rejected(local, sample):
    client, _ = local
    assert (
        upload(client, sample / "01-sharp.png", photographer="   ").status_code == 400
    )
    photo_id = upload(client, sample / "01-sharp.png").json()["added"][0]
    response = client.get(f"/api/photos/{photo_id}/export?metadata=false")
    with Image.open(BytesIO(response.content)) as image:
        assert 315 not in image.getexif() and 33432 not in image.getexif()


def test_only_one_face_model_job_loads_at_a_time(local, sample, monkeypatch):
    import threading

    client, _ = local
    entered, release = threading.Event(), threading.Event()
    constructed = []

    class Matcher:
        def __init__(self, folder):
            constructed.append(True)

        def encode(self, image):
            entered.set()
            assert release.wait(5)
            return [{"embedding": [1.0, 0.0], "box": [0.1, 0.1, 0.2, 0.2]}]

        similarity = staticmethod(FaceMatcher.similarity)

    monkeypatch.setattr("curator.web.FaceMatcher", Matcher)
    payload = (sample / "01-sharp.png").read_bytes()
    result = []

    def request():
        result.append(
            client.post(
                "/api/match",
                headers=HEADERS,
                data={"consent": "true"},
                files=[("files", ("ref.png", payload, "image/png"))],
            )
        )

    worker = threading.Thread(target=request)
    worker.start()
    assert entered.wait(5)
    try:
        second = client.post(
            "/api/match",
            headers=HEADERS,
            data={"consent": "true"},
            files=[("files", ("ref.png", payload, "image/png"))],
        )
        assert second.status_code == 409
        assert len(constructed) == 1
    finally:
        release.set()
        worker.join(5)
    assert result[0].status_code == 200


def test_pixel_bomb_rejected_before_storage(local, sample, monkeypatch):
    client, folder = local
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    result = upload(client, sample / "01-sharp.png")
    assert result.json()["added"] == []
    assert "DecompressionBomb" in result.json()["errors"][0]
    assert client.get("/api/state").json()["count"] == 0
    assert not list((folder / "originals").iterdir())


def test_optimized_previews_use_original_resolution_and_strip_metadata(local, tmp_path):
    client, folder = local
    path = tmp_path / "large.jpg"
    image = Image.new("RGB", (3000, 2000), "navy")
    exif = Image.Exif()
    exif[315] = "Private source metadata"
    image.save(path, quality=95, exif=exif)
    photo_id = upload(client, path).json()["added"][0]
    for endpoint, expected in [("thumb", (1024, 683)), ("preview", (2048, 1365))]:
        response = client.get(f"/api/photos/{photo_id}/{endpoint}")
        assert response.status_code == 200
        assert response.headers["cache-control"].startswith("private")
        with Image.open(BytesIO(response.content)) as preview:
            assert preview.size == expected
            assert not preview.getexif()
        assert (
            client.get(f"/api/photos/{photo_id}/{endpoint}").content == response.content
        )
    assert client.get(f"/api/photos/{photo_id}/original").content == path.read_bytes()
    assert client.get("/api/photos/missing/preview").status_code == 404


def test_pair_comparison_is_explicit_one_to_one_and_never_stored(
    local, sample, monkeypatch
):
    client, folder = local

    class Matcher:
        def __init__(self, folder):
            pass

        def encode(self, image):
            return [{"embedding": [1.0, 0.0], "box": [0.1, 0.2, 0.3, 0.4]}]

        similarity = staticmethod(FaceMatcher.similarity)

    monkeypatch.setattr("curator.web.FaceMatcher", Matcher)
    payload = (sample / "01-sharp.png").read_bytes()
    files = [
        ("files", ("reference.png", payload, "image/png")),
        ("files", ("target.png", payload, "image/png")),
    ]
    assert (
        client.post(
            "/api/match", headers=HEADERS, data={"mode": "pair"}, files=files
        ).status_code
        == 400
    )
    result = client.post(
        "/api/match",
        headers=HEADERS,
        data={"mode": "pair", "consent": "true"},
        files=files,
    )
    assert result.status_code == 200, result.text
    assert result.json()["matched"] and result.json()["target_box"] == [
        0.1,
        0.2,
        0.3,
        0.4,
    ]
    assert client.get("/api/state").json()["count"] == 0
    assert not list((folder / "originals").iterdir())
    assert (
        client.post(
            "/api/match",
            headers=HEADERS,
            data={"mode": "pair", "consent": "true"},
            files=files[:1],
        ).status_code
        == 400
    )


def test_directory_import_is_bounded_and_preserves_sources(local, sample, tmp_path):
    client, folder = local
    original = {p.name: p.read_bytes() for p in sample.iterdir()}
    assert (
        client.post(
            "/api/import",
            headers=HEADERS,
            json={"directory": str(sample), "photographer": "Team"},
        ).status_code
        == 400
    )
    result = client.post(
        "/api/import",
        headers=HEADERS,
        json={"directory": str(sample), "photographer": "Team", "permission": True},
    )
    assert result.status_code == 200, result.text
    state = await_job(client)
    assert not state["job"]["error"] and state["count"] == 6
    assert state["job"]["added"] == 6 and state["job"]["reviewed"] == 6
    assert {p.name: p.read_bytes() for p in sample.iterdir()} == original
    assert (
        client.post(
            "/api/import",
            headers=HEADERS,
            json={"directory": str(folder), "photographer": "Team", "permission": True},
        ).status_code
        == 400
    )


def test_agent_api_uses_real_tool_results_and_preserves_gallery(
    local, sample, monkeypatch
):
    client, _ = local
    upload(client, sample / "01-sharp.png")
    responses = iter(
        [
            (
                {
                    "role": "assistant",
                    "tool_calls": [
                        {"function": {"name": "get_shortlist", "arguments": {}}}
                    ],
                },
                5,
            ),
            ({"role": "assistant", "content": "No picks yet."}, 5),
        ]
    )
    monkeypatch.setattr("curator.agent.ollama_chat", lambda *a, **k: next(responses))
    assert client.post("/api/agent", json={"query": "Show picks"}).status_code == 403
    result = client.post("/api/agent", headers=HEADERS, json={"query": "Show picks"})
    assert result.status_code == 200
    assert not await_job(client)["job"]["error"]
    answer = client.get("/api/agent").json()["result"]
    assert (
        answer["trace"][0]["tool"] == "get_shortlist"
        and answer["photos"] == []
        and answer["tokens"] == 10
    )
    assert client.get("/api/state").json()["count"] == 1


def test_agent_face_count_api_returns_photos_when_final_message_is_empty(
    local, sample, monkeypatch
):
    client, _ = local
    photo_id = upload(client, sample / "01-sharp.png").json()["added"][0]

    class Detector:
        def __init__(self, folder):
            pass

        def detect(self, image):
            return [{"box": [0.1, 0.1, 0.2, 0.2]}, {"box": [0.5, 0.1, 0.2, 0.2]}]

    monkeypatch.setattr("curator.web.FaceMatcher", Detector)
    replies = iter(
        [
            (
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "count_faces",
                                "arguments": {"min_faces": 2},
                            }
                        }
                    ],
                },
                10,
            ),
            ({"role": "assistant", "content": ""}, 5),
        ]
    )
    monkeypatch.setattr("curator.agent.ollama_chat", lambda *a, **k: next(replies))
    assert (
        client.post(
            "/api/agent", headers=HEADERS, json={"query": "Photos with multiple faces"}
        ).status_code
        == 200
    )
    assert not await_job(client)["job"]["error"]
    result = client.get("/api/agent").json()["result"]
    assert [p["id"] for p in result["photos"]] == [photo_id]
    assert (
        result["photos"][0]["face_count"] == 2
        and len(result["photos"][0]["detected_faces"]) == 2
    )
    assert result["answer"].strip() and "1 candidate photos" in result["answer"]
    assert result["trace"][0]["tool"] == "count_faces"
