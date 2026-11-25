"""Gemini TTS with a prebuilt (stock) voice. No voice cloning, ever (ETHICS.md).

Since the 3.8 TTS models, speech goes through the Interactions API (`client.interactions.create`),
not generate_content: the TTS models are not visible to `models.list()` / `models.get()` and
generate_content returns 404 for them (FAILURES.md F03). The style is passed as a
`speech_metadata` annotation, which keeps the spoken text exactly what the storyboard says.
The response is a complete WAV (24 kHz, mono, 16-bit) as base64; raw PCM is also handled.

`synthesize_batch` sends several lines in one request (one turn each, with its own style), which
is how the narration fits the free tier's 10 requests a day (pipeline/narration.py).
"""

from __future__ import annotations

import base64
import io
import wave
from typing import Any

from ..common.env import require
from ..common.retry import RetryableError
from .base import AudioResult, BaseAdapter


LONG_PAUSE = "<long pause>"  # a documented inline pause tag of the 3.8 TTS models


def turn(text: str, style: str | None) -> dict[str, Any]:
    content: dict[str, Any] = {"type": "text", "text": text}
    if style:
        content["annotations"] = [{"type": "speech_metadata", "style": style}]
    return content


def pcm_to_wav(pcm: bytes, rate: int = 24000, channels: int = 1, width: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def wav_info(wav: bytes) -> tuple[int, float, int, int]:
    """(sample_rate, duration_s, channels, sample_width) of a WAV byte string."""
    with wave.open(io.BytesIO(wav), "rb") as w:
        rate, frames = w.getframerate(), w.getnframes()
        return rate, frames / float(rate), w.getnchannels(), w.getsampwidth()


class GeminiTTS(BaseAdapter):
    name = "gemini_tts"

    def __init__(self, model: str, **params: Any):
        super().__init__(model, **params)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(
                api_key=require("GEMINI_API_KEY", why="narration (Gemini TTS) stage"),
                http_options={"api_version": self.params.get("api_version", "v1beta")},
            )
        return self._client

    def synthesize(self, text: str, voice: str, style: str | None = None) -> AudioResult:
        return self._speak([turn(text, style)], voice)

    def synthesize_batch(self, items: list[tuple[str, str | None]], voice: str) -> AudioResult:
        """Several lines in ONE request (the free tier allows 10 TTS requests a day).

        Each line is its own turn with its own style annotation (the docs: "split the script into
        separate turns with distinct `style` values for each turn"), and a documented
        `<long pause>` tag ends every turn but the last, so the narration stage can cut the audio
        at the pauses (pipeline/common/audio.py split_points).
        """
        turns = [turn(text + (f" {LONG_PAUSE}" if i < len(items) - 1 else ""), style)
                 for i, (text, style) in enumerate(items)]
        return self._speak(turns, voice)

    def _speak(self, content: list[dict], voice: str) -> AudioResult:
        interaction = self.client.interactions.create(
            model=self.model,
            input=[{"type": "user_input", "content": content}],
            response_format={"type": "audio"},
            generation_config={"speech_config": [{"voice": voice}]},
        )
        audio = getattr(interaction, "output_audio", None)
        data = getattr(audio, "data", None) if audio is not None else None
        if not data:
            # Seen occasionally with TTS models: a turn with no audio. A retry usually works.
            raise RetryableError(f"no audio in response (status={getattr(interaction, 'status', None)})")
        raw = base64.b64decode(data) if isinstance(data, str) else bytes(data)
        mime = getattr(audio, "mime_type", None) or "audio/wav"
        if raw[:4] != b"RIFF":  # headerless PCM (audio/l16)
            raw = pcm_to_wav(raw, rate=int(self.params.get("sample_rate", 24000)))
        rate, duration, channels, width = wav_info(raw)
        usage = getattr(interaction, "usage", None)
        meta = {
            "mime": mime, "channels": channels, "sample_width": width, "voice": voice,
            "interaction_id": getattr(interaction, "id", None),
            "usage": _usage_dict(usage),
        }
        return AudioResult(raw, rate, duration, meta)


def _usage_dict(usage: Any) -> dict | None:
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return {k: v for k, v in usage.model_dump().items() if v is not None}
    return {"raw": str(usage)}
