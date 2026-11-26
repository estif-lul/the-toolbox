"""Shared Kaggle mechanics for the batch-async stages (Wan clips, ACE-Step music).

One round trip:
1. **Stage the inputs** in `outputs/.kaggle_staging/<stage>/dataset/` (gitignored): `jobs.json`
   plus the files it names (keyframes), and push them as a private dataset
   `<user>/toolbox-<stage>-jobs` (create the first time, a new version afterwards). Wait until it is ready.
2. **Push the kernel** (a private script kernel, GPU T4 x2, internet on) from
   `outputs/.kaggle_staging/<stage>/kernel/`. The sha256 of `jobs.json` is written into the script
   (`EXPECTED_JOBS_SHA`) so a kernel that mounts a stale dataset version refuses to run.
3. **Poll** `kernels status` and **pull** `kernels output` (the clips, `results.jsonl`, `env.json`,
   the log). The kernel writes results as it goes, so a session that dies still leaves its finished work.

The Kaggle username is read from the CLI config at run time and is never written to a tracked
file. Every CLI call is logged as an `external_job` line in runs.jsonl.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ..common import env
from ..common.cache import OUTPUTS, atomic_write_json, atomic_write_text, file_sha256, rel
from ..common.log import log_event, now_iso

KERNELS = env.ROOT / "pipeline" / "kaggle"
STAGING = OUTPUTS / ".kaggle_staging"
ACCELERATOR = "NvidiaTeslaT4"   # "GPU T4 x2"; P100 is retired (COSTS.md)
STATUSES = ("queued", "running", "complete", "error", "cancel")


class KaggleError(RuntimeError):
    """A Kaggle CLI call failed (the message carries the CLI's own error text, redacted)."""


def cli() -> str:
    exe_dir = Path(sys.executable).parent
    for name in ("kaggle.exe", "kaggle"):
        if (exe_dir / name).exists():
            return str(exe_dir / name)
    found = shutil.which("kaggle")
    if not found:
        raise KaggleError("kaggle CLI not found; run `make setup`")
    return found


def run_cli(args: list[str], *, stage: str, check: bool = True, timeout: int = 900,
            log: bool = True) -> subprocess.CompletedProcess:
    """Run `kaggle <args>` with the .env credentials; log it (status polls are not logged: they would
    flood runs.jsonl); raise KaggleError on failure if `check`."""
    env.load_env()
    if not env.kaggle_auth_available():
        raise env.MissingKeyError(f"Kaggle credentials not found. Get them from: {env.WHERE['KAGGLE_API_TOKEN']}")
    t0 = time.perf_counter()
    proc = subprocess.run([cli(), *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)
    out = env.redact((proc.stdout or "") + (proc.stderr or ""))
    proc.stdout, proc.stderr = env.redact(proc.stdout or ""), env.redact(proc.stderr or "")
    ok = proc.returncode == 0
    if log or not ok:
        log_event("external_job", stage=stage, provider="kaggle", model="kaggle-cli",
                  params={"cmd": " ".join(str(a) for a in args[:2])}, latency_s=time.perf_counter() - t0,
                  status="ok" if ok else "error", error=None if ok else out[-400:])
    if check and not ok:
        raise KaggleError(f"kaggle {' '.join(map(str, args[:2]))} failed: {out.strip()[-600:]}")
    return proc


_USER: str | None = None


def username() -> str:
    global _USER
    if _USER:
        return _USER
    env.load_env()
    user = env.get("KAGGLE_USERNAME")
    if not user:
        text = run_cli(["config", "view"], stage="kaggle").stdout
        m = re.search(r"username:\s*(\S+)", text)
        if not m or m.group(1) == "None":
            raise KaggleError("could not read the Kaggle username from `kaggle config view`")
        user = m.group(1)
    _USER = user
    return user


def scrub(text: str) -> str:
    """Replace the Kaggle username with <user> in text that goes into a tracked file."""
    return text.replace(username(), "<user>") if text else text


def dataset_slug(stage: str) -> str:
    return f"toolbox-{stage}-jobs"


def kernel_slug(stage: str) -> str:
    return f"toolbox-{stage}"


def jobs_text(payload: dict) -> str:
    return json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def stage_dataset(stage: str, payload: dict, files: dict[str, Path]) -> tuple[Path, str]:
    """Write jobs.json + its files into a clean staging folder. Returns (folder, sha256 of jobs.json)."""
    d = STAGING / stage / "dataset"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    for name, src in files.items():
        shutil.copyfile(src, d / name)
    atomic_write_text(d / "jobs.json", jobs_text(payload))
    atomic_write_json(d / "dataset-metadata.json", {
        "title": f"toolbox {stage} jobs", "id": f"{username()}/{dataset_slug(stage)}",
        "licenses": [{"name": "CC0-1.0"}]})
    return d, file_sha256(d / "jobs.json")


def dataset_status(stage: str) -> str | None:
    proc = run_cli(["datasets", "status", f"{username()}/{dataset_slug(stage)}"], stage=stage, check=False, log=False)
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip().lower() or None


def push_dataset(stage: str, folder: Path, sha: str, *, wait_s: int = 600) -> None:
    if dataset_status(stage) is None:
        run_cli(["datasets", "create", "-p", folder], stage=stage)
    else:
        run_cli(["datasets", "version", "-p", folder, "-m", f"jobs {sha[:12]}"], stage=stage)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        time.sleep(10)
        if (dataset_status(stage) or "").startswith("ready"):
            return
    raise KaggleError(f"dataset {dataset_slug(stage)} not ready after {wait_s}s")


def push_kernel(stage: str, script: Path, sha: str, *, accelerator: str = ACCELERATOR) -> str:
    """Template the job hash into the script, write kernel-metadata.json, push. Returns the CLI text."""
    d = STAGING / stage / "kernel"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    code = script.read_text(encoding="utf-8")
    if 'EXPECTED_JOBS_SHA = ""' not in code:
        raise KaggleError(f"{script.name} has no `EXPECTED_JOBS_SHA = \"\"` line to template")
    atomic_write_text(d / script.name, code.replace('EXPECTED_JOBS_SHA = ""', f'EXPECTED_JOBS_SHA = "{sha}"', 1))
    user = username()
    atomic_write_json(d / "kernel-metadata.json", {
        "id": f"{user}/{kernel_slug(stage)}", "title": kernel_slug(stage), "code_file": script.name,
        "language": "python", "kernel_type": "script", "is_private": True, "enable_gpu": True,
        "enable_tpu": False, "enable_internet": True, "dataset_sources": [f"{user}/{dataset_slug(stage)}"],
        "competition_sources": [], "kernel_sources": [], "model_sources": []})
    return run_cli(["kernels", "push", "-p", d, "--accelerator", accelerator], stage=stage).stdout.strip()


def kernel_status(stage: str) -> str:
    """queued | running | complete | error | cancel (or the CLI's raw text if it is none of these)."""
    text = run_cli(["kernels", "status", f"{username()}/{kernel_slug(stage)}"], stage=stage, log=False).stdout
    return parse_status(text)


def parse_status(text: str) -> str:
    low = text.lower()
    for s in STATUSES:
        if s in low:
            return s
    return text.strip()


def pull_output(stage: str) -> Path:
    """Download the kernel's /kaggle/working into a clean staging folder."""
    d = STAGING / stage / "output"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    run_cli(["kernels", "output", f"{username()}/{kernel_slug(stage)}", "-p", d, "-o"], stage=stage, timeout=1800)
    return d


def read_results(folder: Path) -> list[dict]:
    """results.jsonl rows (the last row per job_id wins); tolerant of a torn last line."""
    rows: dict[str, dict] = {}
    path = folder / "results.jsonl"
    if not path.exists():
        return []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("job_id"):
            rows[row["job_id"]] = row
    return list(rows.values())


def save_handle(stage_dir: Path, handle: dict) -> None:
    atomic_write_json(stage_dir / "kaggle_job.json", {**handle, "saved_at": now_iso()})


def load_handle(stage_dir: Path) -> dict | None:
    p = stage_dir / "kaggle_job.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def wait(stage: str, *, every_s: int = 120, max_s: int = 6 * 3600, say=print) -> str:
    """Poll until the kernel is no longer queued/running."""
    t0 = time.time()
    while True:
        st = kernel_status(stage)
        say(f"{kernel_slug(stage)}: {st} ({(time.time() - t0) / 60:.0f} min)")
        if st not in ("queued", "running") or time.time() - t0 > max_s:
            return st
        time.sleep(every_s)


class KaggleBatch:
    """Mixin for the Kaggle adapters: MediaJob list -> dataset + kernel push; status; output pull."""

    kaggle_stage = ""          # "wan" | "music": names the dataset, kernel and staging folder
    script: Path = Path()

    def payload(self, jobs, extra: dict) -> tuple[dict, dict[str, Path]]:
        rows, files = [], {}
        for j in jobs:
            row = {"job_id": j.job_id, "item": j.shot_id, "prompt": j.prompt, "seed": j.seed, **j.params}
            if j.negative_prompt is not None:
                row["negative_prompt"] = j.negative_prompt
            if j.image_path is not None:
                row["image"] = f"{j.job_id}{Path(j.image_path).suffix}"
                files[row["image"]] = Path(j.image_path)
            rows.append(row)
        return {"model": self.model, **extra, "jobs": rows}, files

    def submit(self, jobs, extra: dict | None = None, *, dry_run: bool = False):
        from .base import JobHandle

        payload, files = self.payload(jobs, extra or {})
        folder, sha = stage_dataset(self.kaggle_stage, payload, files)
        handle = JobHandle(provider=self.name, ref=kernel_slug(self.kaggle_stage), jobs_sha=sha,
                           submitted_at=now_iso(), meta={"jobs": len(payload["jobs"]), "staged": rel(folder)})
        if dry_run:
            handle.meta["dry_run"] = True
            return handle
        push_dataset(self.kaggle_stage, folder, sha)
        handle.meta["push"] = scrub(push_kernel(self.kaggle_stage, self.script, sha))
        m = re.search(r"version\s+(\d+)", handle.meta["push"], re.I)
        handle.meta["version"] = int(m.group(1)) if m else None
        return handle

    def status(self, handle) -> str:
        return kernel_status(self.kaggle_stage)

    def collect(self, handle, out_dir: Path | None = None):
        from .base import VideoResult

        folder = pull_output(self.kaggle_stage)
        results = []
        for row in read_results(folder):
            path = folder / row["file"] if row.get("ok") and row.get("file") else None
            results.append(VideoResult(job_id=row["job_id"], ok=bool(row.get("ok")) and path is not None and path.exists(),
                                       path=path, seconds=row.get("seconds"), meta=row, error=row.get("error")))
        return results, folder
