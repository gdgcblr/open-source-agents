"""Speaker-diarized transcription of recorded audio with Deepgram's pre-recorded API."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

DEEPGRAM_API_URL = "https://api.deepgram.com"
# Long recordings can take a while to process; connecting should still fail fast.
_TIMEOUT = httpx.Timeout(300.0, connect=10.0)


class DeepgramError(RuntimeError):
    """Raised when Deepgram cannot transcribe the audio."""


@dataclass(frozen=True, slots=True)
class DiarizedUtterance:
    speaker: int
    start: float
    end: float
    text: str
    confidence: float


@dataclass(frozen=True, slots=True)
class DiarizationResult:
    utterances: list[DiarizedUtterance]
    duration_seconds: float | None

    @property
    def speaker_count(self) -> int:
        return len({utterance.speaker for utterance in self.utterances})


class DeepgramDiarizer:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        language: str | None = None,
        language_hints: list[str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._language = language
        self._language_hints = language_hints or []
        self._transport = transport

    async def diarize(self, audio: bytes, content_type: str) -> DiarizationResult:
        params: dict[str, str | list[str]] = {
            "model": self._model,
            "diarize_model": "latest",
            "utterances": "true",
            "smart_format": "true",
            "punctuate": "true",
        }
        if self._language:
            params["language"] = self._language
        if self._language == "multi" and self._language_hints:
            # Repeated parameter: biases code-switching detection toward these languages.
            params["language_hint"] = self._language_hints
        headers = {"Authorization": f"Token {self._api_key}", "Content-Type": content_type}

        async with httpx.AsyncClient(
            base_url=DEEPGRAM_API_URL, timeout=_TIMEOUT, transport=self._transport
        ) as client:
            try:
                response = await client.post(
                    "/v1/listen", params=params, headers=headers, content=audio
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:300]
                raise DeepgramError(
                    f"Deepgram returned HTTP {exc.response.status_code}: {detail}"
                ) from exc
            except httpx.HTTPError as exc:
                raise DeepgramError(f"Could not reach Deepgram: {exc}") from exc

        return parse_diarized_response(response.json())


def parse_diarized_response(payload: Mapping[str, Any]) -> DiarizationResult:
    """Extract speaker-attributed utterances from a `/v1/listen?utterances=true` response."""
    utterances = [
        DiarizedUtterance(
            speaker=int(item.get("speaker", 0)),
            start=float(item["start"]),
            end=float(item["end"]),
            text=item["transcript"].strip(),
            confidence=float(item.get("confidence", 0.0)),
        )
        for item in payload.get("results", {}).get("utterances", [])
        if item.get("transcript", "").strip()
    ]
    duration = payload.get("metadata", {}).get("duration")
    return DiarizationResult(
        utterances=utterances,
        duration_seconds=float(duration) if duration is not None else None,
    )
