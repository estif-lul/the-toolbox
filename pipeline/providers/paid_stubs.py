"""The paid / frontier lane, designed in now, implemented later.

Each class has the same signature as its free counterpart, so implementing one is a single file
plus a config line in config/providers.yaml (profile `paid`). Until then they fail loudly, and the
`paid` profile lists the free adapter as the fallback so nothing silently changes provider.
Before implementing one: record its list price (config/prices.yaml, with URL and date), its
licence/output terms, provenance (SynthID / C2PA) and data retention (ETHICS.md).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from ..common.retry import FatalError
from .base import AudioResult, BaseAdapter, ImageResult, JobHandle, MediaJob, TextResult, VideoResult

DOC = "see docs/PAID_LANE.md"


class _Stub(BaseAdapter):
    candidates = ""

    def _todo(self, *_: Any, **__: Any):
        # FatalError (not NotImplementedError) so invoke() stops instead of retrying a stub.
        raise FatalError(f"{type(self).__name__} ({self.model}) is not implemented yet: {DOC}. "
                         f"Candidates: {self.candidates}")


class PaidText(_Stub):
    name = "paid_text"
    candidates = "Gemini paid tier (same adapter, higher limits, no training on data); Claude via the Anthropic API"

    def generate_json(self, prompt: str, schema: dict | None = None) -> TextResult:
        self._todo()


class PaidTTS(_Stub):
    name = "paid_tts"
    candidates = "Gemini TTS paid tier; ElevenLabs (stock voices only, never cloning without consent)"

    def synthesize(self, text: str, voice: str, style: str | None = None) -> AudioResult:
        self._todo()


class PaidImage(_Stub):
    name = "paid_image"
    candidates = "Nano Banana (Gemini image); FLUX.2 pro/flex via the BFL API or fal.ai (multi-reference)"

    def generate(self, prompt: str, seed: int, w: int, h: int, refs: Sequence[Path] = (),
                 steps: int | None = None) -> ImageResult:
        self._todo()


class _AsyncStub(_Stub):
    def submit(self, jobs: Sequence[MediaJob]) -> JobHandle:
        self._todo()

    def status(self, handle: JobHandle) -> str:
        self._todo()

    def collect(self, handle: JobHandle, out_dir: Path) -> list[VideoResult]:
        self._todo()


class PaidVideo(_AsyncStub):
    name = "paid_video"
    candidates = "Gemini Omni Flash video; Wan 2.2 A14B / Kling via fal.ai or Replicate"


class RentedGpuVideo(_AsyncStub):
    name = "rented_gpu_video"
    candidates = "the same Wan 2.2 job script (main(jobs_path, out_dir)) on RunPod or Modal, L40S / A100 / H100"


class PaidMusic(_AsyncStub):
    name = "paid_music"
    candidates = "Lyria 3.5; ACE-Step 1.5 on a rented GPU"
