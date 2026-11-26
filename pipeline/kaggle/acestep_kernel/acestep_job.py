# toolbox-music: ACE-Step 1.5 score candidates for "The Toolbox", run as a Kaggle script kernel
# (GPU T4 x2, internet on). Pushed by `make music` (pipeline/providers/kaggle_common.py), which
# writes the sha256 of jobs.json into EXPECTED_JOBS_SHA below.
#
# Install: the repo's own locked environment (`uv sync`, as its README says) in a separate venv,
# so Kaggle's preinstalled packages are not disturbed. Generation runs in that venv through a small
# runner script (written below) that calls the documented Python API
# (acestep.handler.AceStepHandler + acestep.inference.generate_music), DiT only (no 5Hz LM:
# thinking off, BPM/key/duration given), one call per seed so each candidate maps to its seed.
# Outputs (/kaggle/working): <job_id>.wav, results.jsonl, env.json, status.json.

EXPECTED_JOBS_SHA = ""

import glob
import hashlib
import json
import os
import subprocess
import sys
import time

T0 = time.time()
WORK = "/kaggle/working"


def log(msg):
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


def write_json(name, obj):
    with open(os.path.join(WORK, name), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1)


hits = sorted(glob.glob("/kaggle/input/**/jobs.json", recursive=True))
if not hits:
    raise SystemExit("jobs.json not found under /kaggle/input")
with open(hits[0], "rb") as fh:
    RAW = fh.read()
SHA = hashlib.sha256(RAW).hexdigest()
if EXPECTED_JOBS_SHA and SHA != EXPECTED_JOBS_SHA:
    write_json("status.json", {"phase": "stale_dataset", "jobs_sha": SHA, "expected": EXPECTED_JOBS_SHA})
    raise SystemExit(f"stale dataset: jobs.json sha {SHA[:12]} != expected {EXPECTED_JOBS_SHA[:12]}")
CFG = json.loads(RAW.decode("utf-8"))
write_json("status.json", {"phase": "install", "jobs_sha": SHA})
log(f"{len(CFG['jobs'])} job(s), jobs.json {SHA[:12]}")

TMP = "/kaggle/tmp" if os.path.isdir("/kaggle/tmp") else "/tmp"
REPO = os.path.join(TMP, "ACE-Step-1.5")
ENV = {"jobs_sha": SHA, "repo": CFG["repo"]}


def sh(cmd, **kw):
    log("$ " + (cmd if isinstance(cmd, str) else " ".join(cmd)))
    return subprocess.run(cmd, shell=isinstance(cmd, str), check=True, **kw)


t = time.time()
sh(["git", "clone", "--depth", "1", CFG["repo"], REPO])
ENV["commit"] = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
sh([sys.executable, "-m", "pip", "install", "-q", "uv"])
PY = os.path.join(REPO, ".venv", "bin", "python")
try:
    sh(["uv", "sync", "--no-dev"], cwd=REPO)
    ENV["install"] = "uv sync"
except subprocess.CalledProcessError as exc:
    log(f"uv sync failed ({exc}); falling back to pip on Kaggle's torch")
    PY = sys.executable
    sh([PY, "-m", "pip", "install", "-q", "--no-deps", "-e", REPO])
    sh([PY, "-m", "pip", "install", "-q", "transformers>=4.51.0,<4.58.0", "diffusers>=0.37.0", "accelerate>=1.12.0",
        "soundfile", "loguru", "einops", "vector-quantize-pytorch", "huggingface_hub", "safetensors", "numba"])
    ENV["install"] = "pip --no-deps + core deps"
ENV["install_s"] = round(time.time() - t, 1)
ENV["versions"] = subprocess.run([PY, "-c", "import torch,sys;print(sys.version.split()[0],torch.__version__,torch.version.cuda,"
                                  "torch.cuda.get_device_name(0))"], capture_output=True, text=True).stdout.strip()
write_json("env.json", ENV)
log(f"installed in {ENV['install_s']}s: {ENV['versions']}")

RUNNER = r'''
import inspect, json, os, sys, time, traceback
CFG = json.load(open(sys.argv[1], encoding="utf-8"))
WORK, REPO = sys.argv[2], sys.argv[3]
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import GenerationParams, GenerationConfig, generate_music

def accepted(fn, kw):
    sig = inspect.signature(fn)
    if any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
        return kw
    return {k: v for k, v in kw.items() if k in sig.parameters}

def fields(cls, kw):
    names = getattr(cls, "__dataclass_fields__", None) or inspect.signature(cls).parameters
    return {k: v for k, v in kw.items() if k in names}

print("initialize_service", inspect.signature(AceStepHandler.initialize_service), flush=True)
t = time.time()
dit = AceStepHandler()
init = dit.initialize_service(**accepted(dit.initialize_service, dict(
    project_root=REPO, config_path=CFG["jobs"][0].get("config_path", "acestep-v15-turbo"), device="cuda",
    offload_to_cpu=False)))
print("init:", init, round(time.time() - t, 1), "s", flush=True)
llm = LLMHandler()
for job in CFG["jobs"]:
    row = {"job_id": job["job_id"], "item": job["item"], "seed": job["seed"]}
    t = time.time()
    try:
        params = GenerationParams(**fields(GenerationParams, dict(
            caption=job.get("caption") or job["prompt"], lyrics="[Instrumental]", instrumental=True, bpm=job["bpm"],
            keyscale=job["keyscale"], timesignature=job.get("timesignature", "4"), duration=job["duration_s"],
            inference_steps=job["steps"], seed=job["seed"], shift=job.get("shift", 3.0), thinking=False,
            use_cot_metas=False, use_cot_caption=False, use_cot_language=False, use_cot_lyrics=False)))
        config = GenerationConfig(**fields(GenerationConfig, dict(
            batch_size=1, use_random_seed=False, seeds=[job["seed"]], audio_format="flac")))
        out_dir = os.path.join(WORK, "gen_" + job["job_id"])
        res = generate_music(dit, llm, params, config, save_dir=out_dir)
        if not getattr(res, "success", False):
            raise RuntimeError(f"generate_music: {getattr(res, 'error', None) or getattr(res, 'status_message', '')}")
        audio = res.audios[0]
        src = audio["path"]
        dst = os.path.join(WORK, job["job_id"] + os.path.splitext(src)[1])
        os.replace(src, dst)
        row.update(ok=True, file=os.path.basename(dst), sample_rate=audio.get("sample_rate"),
                   params_used={k: v for k, v in (audio.get("params") or {}).items()
                                if isinstance(v, (int, float, str, bool)) or v is None})
    except Exception as exc:
        row.update(ok=False, error=f"{type(exc).__name__}: {exc}", trace=traceback.format_exc()[-1500:])
    row["seconds"] = round(time.time() - t, 1)
    try:
        import torch
        row["gpu_name"] = torch.cuda.get_device_name(0)
        row["peak_vram_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 2)
    except Exception:
        pass
    with open(os.path.join(WORK, "results.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    print(json.dumps({k: v for k, v in row.items() if k != "trace"}), flush=True)
'''
runner = os.path.join(TMP, "acestep_runner.py")
with open(runner, "w", encoding="utf-8") as fh:
    fh.write(RUNNER)
write_json("status.json", {"phase": "generating", "jobs_sha": SHA})
env = dict(os.environ, ACESTEP_CHECKPOINTS_DIR=os.path.join(REPO, "checkpoints"), PYTHONUNBUFFERED="1")
proc = subprocess.run([PY, runner, hits[0], WORK, REPO], cwd=REPO, env=env)
ENV["runner_exit"] = proc.returncode
write_json("env.json", ENV)
write_json("status.json", {"phase": "done", "jobs_sha": SHA, "seconds": round(time.time() - T0, 1)})
log(f"done (runner exit {proc.returncode})")
