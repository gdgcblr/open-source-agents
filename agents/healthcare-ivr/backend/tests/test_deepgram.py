import httpx
import pytest

from app.services.deepgram import DeepgramDiarizer, DeepgramError, parse_diarized_response
from tests.conftest import load_fixture


def test_parse_diarized_response_keeps_speaker_turns() -> None:
    result = parse_diarized_response(load_fixture("deepgram_diarized_call.json"))

    assert result.duration_seconds == 18.4
    assert result.speaker_count == 2
    assert [(u.speaker, u.text) for u in result.utterances] == [
        (0, "Thank you for calling MedCare General Hospital. How can I help you today?"),
        (1, "Hi, when is the cardiology OPD open this week?"),
        (
            0,
            "Cardiology OPD is open Monday to Saturday. Would you like an appointment?",
        ),
        (1, "Yes, with Dr. Arjun Menon, please."),
    ]


def test_parse_handles_responses_without_utterances() -> None:
    result = parse_diarized_response({"metadata": {}, "results": {"channels": []}})

    assert result.utterances == []
    assert result.speaker_count == 0
    assert result.duration_seconds is None


@pytest.mark.anyio
async def test_diarize_requests_diarized_utterances() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=load_fixture("deepgram_diarized_call.json"))

    diarizer = DeepgramDiarizer("dg-key", "nova-3", transport=httpx.MockTransport(handler))
    result = await diarizer.diarize(b"audio-bytes", "audio/mpeg")

    [request] = requests
    assert request.url.path == "/v1/listen"
    assert request.url.params["model"] == "nova-3"
    assert request.url.params["diarize_model"] == "latest"
    assert request.url.params["utterances"] == "true"
    assert request.headers["authorization"] == "Token dg-key"
    assert request.headers["content-type"] == "audio/mpeg"
    assert request.content == b"audio-bytes"
    assert len(result.utterances) == 4


@pytest.mark.anyio
async def test_diarize_wraps_http_errors() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(401, text="Invalid credentials"))
    diarizer = DeepgramDiarizer("bad-key", "nova-3", transport=transport)

    with pytest.raises(DeepgramError, match="HTTP 401"):
        await diarizer.diarize(b"audio", "audio/wav")


@pytest.mark.anyio
async def test_multilingual_recordings_are_transcribed_with_language_hints() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=load_fixture("deepgram_diarized_call.json"))

    diarizer = DeepgramDiarizer(
        "dg-key",
        "nova-3",
        language="multi",
        language_hints=["en", "hi"],
        transport=httpx.MockTransport(handler),
    )
    await diarizer.diarize(b"audio", "audio/mpeg")

    [request] = requests
    assert request.url.params["language"] == "multi"
    assert request.url.params.get_list("language_hint") == ["en", "hi"]
    assert request.url.params["diarize_model"] == "latest"
