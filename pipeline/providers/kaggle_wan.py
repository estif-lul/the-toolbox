"""Wan 2.2 TI2V-5B on a Kaggle GPU kernel (batch-async): `pipeline/kaggle/wan_kernel/wan_job.py`.

submit -> a private dataset (jobs.json + the keyframes) and a script kernel on T4 x2;
status -> `kaggle kernels status`; collect -> `kaggle kernels output` + results.jsonl.
The stage logic (which shots are stale, ingesting clips into the cache) is in pipeline/shots.py.
"""

from __future__ import annotations

from .base import BaseAdapter
from .kaggle_common import KERNELS, KaggleBatch


class KaggleWan(KaggleBatch, BaseAdapter):
    name = "kaggle_wan"
    kaggle_stage = "wan"
    script = KERNELS / "wan_kernel" / "wan_job.py"
