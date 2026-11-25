"""Wan 2.2 TI2V-5B on a Kaggle GPU kernel (batch-async). Implemented in Step 4 (PLAN.md §8).

The signatures are fixed now so the registry, config and fallback chain (Wan -> Ken Burns) are real.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..common.retry import FatalError
from .base import BaseAdapter, JobHandle, MediaJob, VideoResult


class KaggleWan(BaseAdapter):
    name = "kaggle_wan"

    def submit(self, jobs: Sequence[MediaJob]) -> JobHandle:
        raise FatalError("kaggle_wan is implemented in Step 4 (PLAN.md §8)")

    def status(self, handle: JobHandle) -> str:
        raise FatalError("kaggle_wan is implemented in Step 4 (PLAN.md §8)")

    def collect(self, handle: JobHandle, out_dir: Path) -> list[VideoResult]:
        raise FatalError("kaggle_wan is implemented in Step 4 (PLAN.md §8)")
