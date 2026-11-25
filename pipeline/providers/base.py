"""Provider protocols and result types.

Text, TTS and image providers are synchronous (one request, one result). Video and music
providers are batch-async (`submit` -> `status` -> `collect`), because Kaggle kernels and most
paid video APIs work that way. A paid adapter only has to match these signatures (docs/PAID_LANE.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Sequence, runtime_checkable


@dataclass
class TextResult:
    data: Any
    raw_text: str
    meta: dict = field(default_factory=dict)


@dataclass
class AudioResult:
    wav_bytes: bytes
    sample_rate: int
    duration_s: float
    meta: dict = field(default_factory=dict)


@dataclass
class ImageResult:
    data: bytes
    mime: str
    width: int
    height: int
    seed: int | None
    meta: dict = field(default_factory=dict)


@dataclass
class VideoResult:
    job_id: str
    ok: bool
    path: Path | None
    seconds: float | None = None
    meta: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class MediaJob:
    """One unit of async work: a Wan clip or an ACE-Step candidate."""
    job_id: str
    shot_id: str | None
    prompt: str
    seed: int | None
    params: dict = field(default_factory=dict)
    image_path: Path | None = None
    negative_prompt: str | None = None


@dataclass
class JobHandle:
    provider: str
    ref: str               # e.g. "<user>/toolbox-wan" + kernel version
    jobs_sha: str          # hash of the job list (guards against stale inputs)
    submitted_at: str
    meta: dict = field(default_factory=dict)


@dataclass
class MusicResult(VideoResult):
    pass


class Provider(Protocol):
    name: str
    model: str
    params: dict


@runtime_checkable
class TextProvider(Provider, Protocol):
    def generate_json(self, prompt: str, schema: dict | None = None) -> TextResult: ...


@runtime_checkable
class TTSProvider(Provider, Protocol):
    def synthesize(self, text: str, voice: str, style: str | None = None) -> AudioResult: ...


@runtime_checkable
class ImageProvider(Provider, Protocol):
    def generate(self, prompt: str, seed: int, w: int, h: int, refs: Sequence[Path] = (),
                 steps: int | None = None) -> ImageResult: ...


@runtime_checkable
class VideoProvider(Provider, Protocol):
    def submit(self, jobs: Sequence[MediaJob]) -> JobHandle: ...
    def status(self, handle: JobHandle) -> str: ...  # queued | running | complete | error
    def collect(self, handle: JobHandle, out_dir: Path) -> list[VideoResult]: ...


@runtime_checkable
class MusicProvider(Provider, Protocol):
    def submit(self, jobs: Sequence[MediaJob]) -> JobHandle: ...
    def status(self, handle: JobHandle) -> str: ...
    def collect(self, handle: JobHandle, out_dir: Path) -> list[MusicResult]: ...


class BaseAdapter:
    """Common constructor: every adapter is built from one config entry {provider, model, params}."""

    name = "base"

    def __init__(self, model: str, **params: Any):
        self.model = model
        self.params = params
        self.min_interval_s = float(params.get("min_interval_s", 0) or 0)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(model={self.model!r})"
