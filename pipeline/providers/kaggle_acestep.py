"""ACE-Step 1.5 on a Kaggle GPU kernel (batch-async): `pipeline/kaggle/acestep_kernel/acestep_job.py`.

Same round trip as the Wan adapter (kaggle_common.KaggleBatch); no input files, only jobs.json.
The stage logic (candidates per cue, ingest, audition) is in pipeline/music.py.
"""

from __future__ import annotations

from .base import BaseAdapter
from .kaggle_common import KERNELS, KaggleBatch


class KaggleAceStep(KaggleBatch, BaseAdapter):
    name = "kaggle_acestep"
    kaggle_stage = "music"
    script = KERNELS / "acestep_kernel" / "acestep_job.py"
