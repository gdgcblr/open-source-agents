import json
from io import BytesIO
from unittest.mock import Mock

import pytest

from curator.agent import PhotoAgent, visual_assessment
from curator.faces import match_faces


def call(name, args=None):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": args or {}}}],
    }


def test_agent_chooses_executes_observes_and_finishes(monkeypatch):
    replies = iter(
        [
            (call("visual_search", {"query": "changed by model"}), 10),
            ({"role": "assistant", "content": "Found one matching photo."}, 20),
        ]
    )
    received = []

    def chat(messages, *args, **kwargs):
        received.append(list(messages))
        return next(replies)

    monkeypatch.setattr("curator.agent.ollama_chat", chat)
    tool = Mock(
        return_value={"photos": [{"id": "real-id"}], "summary": "One visible logo."}
    )
    result = PhotoAgent().run("Photos with Google logo", {"visual_search": tool})
    tool.assert_called_once_with(query="Photos with Google logo")
    assert (
        result["photos"] == [{"id": "real-id"}]
        and result["tokens"] == 30
        and result["steps"] == 2
    )
    assert received[1][-1]["role"] == "tool"
    assert result["trace"][0]["tool"] == "visual_search"


@pytest.mark.parametrize(
    "name,args",
    [
        ("shell", {}),
        ("count_faces", {"min_faces": True}),
        ("count_faces", {"min_faces": 3, "max_faces": 1}),
        ("inspect_event", {"path": "/etc/passwd"}),
    ],
)
def test_agent_rejects_untrusted_tool_calls(monkeypatch, name, args):
    monkeypatch.setattr(
        "curator.agent.ollama_chat", lambda *a, **k: (call(name, args), 1)
    )
    tool = Mock()
    with pytest.raises(RuntimeError):
        PhotoAgent().run("Find photos", {name: tool})
    tool.assert_not_called()


def test_repeated_tool_loop_and_unbacked_answer_are_stopped(monkeypatch):
    monkeypatch.setattr(
        "curator.agent.ollama_chat", lambda *a, **k: (call("inspect_event"), 1)
    )
    tool = Mock(return_value={"count": 2})
    with pytest.raises(RuntimeError, match="repeated"):
        PhotoAgent().run("Count photos", {"inspect_event": tool})
    assert tool.call_count == 1
    monkeypatch.setattr(
        "curator.agent.ollama_chat", lambda *a, **k: ({"content": "Invented photos"}, 1)
    )
    with pytest.raises(RuntimeError, match="without using a tool"):
        PhotoAgent().run("Find photos", {})


def test_visual_decisions_are_cached_and_validated(tmp_path, monkeypatch):
    chat = Mock(
        return_value=(
            {"content": json.dumps({"match": True, "reason": "Visible logo"})},
            40,
        )
    )
    monkeypatch.setattr("curator.agent.ollama_chat", chat)
    assert visual_assessment(b"image", "hash", "logo", "local", tmp_path)[1:] == (40, 0)
    assert visual_assessment(b"image", "hash", "logo", "local", tmp_path)[1:] == (0, 1)
    assert chat.call_count == 1
    chat.return_value = (
        {"content": json.dumps({"match": "yes", "reason": "Guess"})},
        1,
    )
    with pytest.raises(RuntimeError):
        visual_assessment(b"image", "hash", "other", "local", tmp_path)


def test_face_matches_have_coordinates_one_target_per_person_and_ambiguity():
    refs = [{"embedding": [1, 0]}]
    faces = [
        {"embedding": [1, 0], "box": [0.1, 0.2, 0.2, 0.3]},
        {"embedding": [0.99, 0.1], "box": [0.5, 0.2, 0.2, 0.3]},
    ]
    result = match_faces(refs, faces, 0.45)
    assert (
        len(result) == 1
        and result[0]["box"] == faces[0]["box"]
        and result[0]["ambiguous"]
    )
    assert not match_faces(refs, [{"embedding": [0, 1], "box": [0, 0, 0.2, 0.2]}], 0.45)


@pytest.mark.parametrize("content", ["", "  ", None])
@pytest.mark.parametrize("photo_ids", [[], ["real-photo-a", "real-photo-b"]])
def test_successful_face_results_survive_empty_model_narration(
    monkeypatch, content, photo_ids
):
    replies = iter(
        [
            (call("count_faces", {"min_faces": 2}), 20),
            ({"role": "assistant", "content": content}, 10),
        ]
    )
    chat = Mock(side_effect=lambda *a, **k: next(replies))
    monkeypatch.setattr("curator.agent.ollama_chat", chat)
    tool = Mock(
        return_value={
            "photos": [{"id": p} for p in photo_ids],
            "summary": "Counted detectable faces in the event.",
        }
    )
    result = PhotoAgent().run("Photos with multiple faces", {"count_faces": tool})
    assert result["answer"].strip()
    assert str(len(photo_ids)) in result["answer"]
    assert [p["id"] for p in result["photos"]] == photo_ids
    assert result["trace"][0]["tool"] == "count_faces"
    assert result["tokens"] == 30 and result["steps"] == 2
    tool.assert_called_once_with(min_faces=2)
    assert chat.call_count == 2
