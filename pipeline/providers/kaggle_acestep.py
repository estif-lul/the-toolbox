"""ACE-Step 1.5 on a Kaggle GPU kernel (batch-async). Implemented in Step 4."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..common.retry import FatalError
from .base import BaseAdapter, JobHandle, MediaJob, MusicResult


class KaggleAceStep(BaseAdapter):
    name = "kaggle_acestep"

    def submit(self, jobs: Sequence[MediaJob]) -> JobHandle:
        raise FatalError("kaggle_acestep is implemented in Step 4")

    def status(self, handle: JobHandle) -> str:
        raise FatalError("kaggle_acestep is implemented in Step 4")

    def collect(self, handle: JobHandle, out_dir: Path) -> list[MusicResult]:
        raise FatalError("kaggle_acestep is implemented in Step 4")
