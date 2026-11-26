# toolbox-wan: Wan 2.2 TI2V-5B image-to-video for "The Toolbox", run as a Kaggle script kernel
# (GPU T4 x2, internet on). Pushed by `make shots-push` (pipeline/providers/kaggle_common.py),
# which writes the sha256 of jobs.json into EXPECTED_JOBS_SHA below.
#
# Inputs: a private dataset with jobs.json + one keyframe PNG per job.
# Outputs (/kaggle/working, written as each job finishes):
#   <job_id>.mp4, results.jsonl (one line per job), env.json (versions, GPUs), status.json
#
# Memory plan for a T4 (16 GB, no bf16): fp16 everywhere except the VAE (fp32, as the model card
# recommends). Phase A encodes every prompt with the UMT5 text encoder, then frees it.
# Phase B loads one transformer + VAE per GPU and runs one worker thread per GPU.
# Per job: denoise to latents, then decode (on OOM: VAE tiling, then the transformer moved to the
# CPU for the decode). Attention is forced to PyTorch's memory-efficient kernel: on the pilot the
# default path ran out of memory at 704x704x81 (a ~5 GB attention matrix, i.e. the math kernel).
# If that rung fails for any reason: retry once at 576x576, 49 frames with the default attention.
# A job that still fails is recorded and the batch goes on.

EXPECTED_JOBS_SHA = ""

import glob
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback

T0 = time.time()
WORK = "/kaggle/working"
RESULTS = os.path.join(WORK, "results.jsonl")
LOCK = threading.Lock()


def log(msg):
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


def write_json(name, obj):
    with open(os.path.join(WORK, name), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1)


def record(row):
    with LOCK:
        with open(RESULTS, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")


def find_jobs():
    hits = sorted(glob.glob("/kaggle/input/**/jobs.json", recursive=True))
    if not hits:
        raise SystemExit("jobs.json not found under /kaggle/input")
    return hits[0]


JOBS_PATH = find_jobs()
IN_DIR = os.path.dirname(JOBS_PATH)
with open(JOBS_PATH, "rb") as fh:
    RAW = fh.read()
SHA = hashlib.sha256(RAW).hexdigest()
CFG = json.loads(RAW.decode("utf-8"))
write_json("status.json", {"phase": "start", "jobs_sha": SHA, "expected": EXPECTED_JOBS_SHA})
if EXPECTED_JOBS_SHA and SHA != EXPECTED_JOBS_SHA:
    write_json("status.json", {"phase": "stale_dataset", "jobs_sha": SHA, "expected": EXPECTED_JOBS_SHA})
    raise SystemExit(f"stale dataset: jobs.json sha {SHA[:12]} != expected {EXPECTED_JOBS_SHA[:12]}")
JOBS = sorted(CFG["jobs"], key=lambda j: (j.get("priority", 99), j["job_id"]))
log(f"{len(JOBS)} job(s), jobs.json {SHA[:12]} from {IN_DIR}")

# ---- install ---------------------------------------------------------------------------------
PIP = CFG.get("pip") or ["diffusers>=0.35.1", "transformers", "accelerate", "ftfy", "imageio", "imageio-ffmpeg"]
log("pip install " + " ".join(PIP))
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", *PIP], check=True)

import imageio  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402

import diffusers  # noqa: E402
import transformers  # noqa: E402
from diffusers import AutoencoderKLWan, WanImageToVideoPipeline, WanTransformer3DModel  # noqa: E402
from huggingface_hub import snapshot_download  # noqa: E402
from transformers import AutoTokenizer, UMT5EncoderModel  # noqa: E402

NGPU = torch.cuda.device_count()
ENV = {
    "python": sys.version.split()[0], "torch": torch.__version__, "cuda": torch.version.cuda,
    "diffusers": diffusers.__version__, "transformers": transformers.__version__,
    "gpus": [torch.cuda.get_device_name(i) for i in range(NGPU)],
    "jobs_sha": SHA, "model": CFG["model"],
}
write_json("env.json", ENV)
log(f"env: {ENV}")
if NGPU == 0:
    raise SystemExit("no GPU")

# ---- weights ---------------------------------------------------------------------------------
TMP = "/kaggle/tmp" if os.path.isdir("/kaggle/tmp") else "/tmp"
MODEL_DIR = os.path.join(TMP, "wan22_ti2v_5b")
free_gb = shutil.disk_usage(TMP).free / 1e9
log(f"downloading {CFG['model']} into {MODEL_DIR} ({free_gb:.0f} GB free)")
t = time.time()
snapshot_download(CFG["model"], local_dir=MODEL_DIR,
                  allow_patterns=["model_index.json", "scheduler/*", "tokenizer/*", "text_encoder/*",
                                  "transformer/*", "vae/*"])
ENV["download_s"] = round(time.time() - t, 1)
write_json("env.json", ENV)
log(f"download done in {ENV['download_s']}s")

# ---- phase A: text embeddings ----------------------------------------------------------------
MAX_LEN = 512


def clean(text):
    import ftfy
    return " ".join(ftfy.fix_text(text).split())


def t5_embeds(prompts, tok, te, device):
    """The same recipe as diffusers' Wan pipelines: pad to 512, trim each to its length, zero-pad back."""
    inputs = tok([clean(p) for p in prompts], padding="max_length", max_length=MAX_LEN, truncation=True,
                 add_special_tokens=True, return_attention_mask=True, return_tensors="pt")
    ids, mask = inputs.input_ids, inputs.attention_mask
    lens = mask.gt(0).sum(dim=1).long()
    with torch.no_grad():
        emb = te(ids.to(device), mask.to(device)).last_hidden_state
    emb = [u[:v] for u, v in zip(emb, lens)]
    return torch.stack([torch.cat([u, u.new_zeros(MAX_LEN - u.size(0), u.size(1))]) for u in emb]).float().cpu()


t = time.time()
texts = sorted({j["prompt"] for j in JOBS} | {j["negative_prompt"] for j in JOBS})
tok = AutoTokenizer.from_pretrained(MODEL_DIR, subfolder="tokenizer")
te = UMT5EncoderModel.from_pretrained(MODEL_DIR, subfolder="text_encoder", torch_dtype=torch.float16).to("cuda:0")
EMB = {}
for p in texts:
    EMB[p] = t5_embeds([p], tok, te, "cuda:0")
te_mode = "fp16 on GPU"
if any(not torch.isfinite(e).all() for e in EMB.values()):
    log("fp16 text embeddings are not finite: re-encoding on the CPU in bf16")
    del te
    torch.cuda.empty_cache()
    te = UMT5EncoderModel.from_pretrained(MODEL_DIR, subfolder="text_encoder", torch_dtype=torch.bfloat16)
    EMB = {p: t5_embeds([p], tok, te, "cpu") for p in texts}
    te_mode = "bf16 on CPU"
del te
torch.cuda.empty_cache()
ENV["text_encoder"] = {"mode": te_mode, "prompts": len(texts), "seconds": round(time.time() - t, 1)}
write_json("env.json", ENV)
log(f"encoded {len(texts)} prompt(s) ({te_mode}) in {time.time() - t:.0f}s")

# ---- phase B: one pipeline per GPU -----------------------------------------------------------


def load_pipe(i):
    dev = f"cuda:{i}"
    vae = AutoencoderKLWan.from_pretrained(MODEL_DIR, subfolder="vae", torch_dtype=torch.float32)
    tr = WanTransformer3DModel.from_pretrained(MODEL_DIR, subfolder="transformer", torch_dtype=torch.float16)
    pipe = WanImageToVideoPipeline.from_pretrained(MODEL_DIR, transformer=tr, vae=vae, text_encoder=None,
                                                   tokenizer=None, torch_dtype=torch.float16)
    pipe.to(dev)
    pipe.set_progress_bar_config(disable=True)
    return pipe


def decode(pipe, latents, dev):
    """Latents -> uint8 frames. On OOM: VAE tiling, then move the transformer off the GPU."""
    vae = pipe.vae
    cfg = vae.config
    lat = latents.to(dev, vae.dtype)
    mean = torch.tensor(cfg.latents_mean).view(1, cfg.z_dim, 1, 1, 1).to(dev, vae.dtype)
    std = 1.0 / torch.tensor(cfg.latents_std).view(1, cfg.z_dim, 1, 1, 1).to(dev, vae.dtype)
    lat = lat / std + mean
    notes = []
    for attempt in ("plain", "tiling", "transformer_off"):
        try:
            if attempt == "tiling":
                vae.enable_tiling()
            if attempt == "transformer_off":
                pipe.transformer.to("cpu")
            torch.cuda.empty_cache()
            with torch.no_grad():
                video = vae.decode(lat, return_dict=False)[0]
            frames = pipe.video_processor.postprocess_video(video, output_type="np")[0]
            return (np.clip(frames, 0, 1) * 255).round().astype(np.uint8), attempt, notes
        except torch.cuda.OutOfMemoryError:
            notes.append(f"decode OOM ({attempt})")
            torch.cuda.empty_cache()
        finally:
            if attempt == "transformer_off":
                pipe.transformer.to(dev)
    raise RuntimeError("VAE decode out of memory on every rung: " + "; ".join(notes))


def set_attention(pipe, backend):
    try:
        pipe.transformer.set_attention_backend(backend)
        return backend
    except Exception as exc:  # noqa: BLE001
        return f"default ({type(exc).__name__}: {exc})"[:200]


def run_job(pipe, i, job):
    dev = f"cuda:{i}"
    img = Image.open(os.path.join(IN_DIR, job["image"])).convert("RGB")
    rungs = [(job["width"], job["height"], job["frames"], "_native_efficient")]
    rungs.append((min(job["width"], 576), min(job["height"], 576), min(job["frames"], 49), "native"))
    notes = []
    for w, h, n, backend in rungs:
        try:
            attn = set_attention(pipe, backend)
            torch.cuda.reset_peak_memory_stats(dev)
            gen = torch.Generator(device=dev).manual_seed(int(job["seed"]))
            t = time.time()
            with torch.no_grad():
                out = pipe(image=img.resize((w, h), Image.LANCZOS), prompt_embeds=EMB[job["prompt"]].to(dev, torch.float16),
                           negative_prompt_embeds=EMB[job["negative_prompt"]].to(dev, torch.float16),
                           height=h, width=w, num_frames=n, num_inference_steps=job["steps"],
                           guidance_scale=job["guidance"], generator=gen, output_type="latent")
            latents = out.frames
            denoise_s = time.time() - t
            if not torch.isfinite(latents).all():
                raise FloatingPointError("latents are not finite (fp16 overflow)")
            frames, how, dnotes = decode(pipe, latents, dev)
            notes += dnotes
            return frames, {"width": w, "height": h, "frames": n, "steps": job["steps"], "guidance": job["guidance"],
                            "fps": job["fps"], "denoise_s": round(denoise_s, 1), "decode": how,
                            "attention": attn}, notes
        except Exception as exc:  # noqa: BLE001 - OOM or an unsupported attention kernel: next rung
            kind = "OOM" if isinstance(exc, torch.cuda.OutOfMemoryError) else f"{type(exc).__name__}: {str(exc)[:160]}"
            notes.append(f"denoise failed at {w}x{h}x{n} ({backend}): {kind}")
            log(f"{job['item']}: {kind} at {w}x{h}x{n} ({backend}), trying the next rung")
            torch.cuda.empty_cache()
    raise RuntimeError("; ".join(notes))


def save(frames, path, fps):
    w = imageio.get_writer(path, fps=fps, codec="libx264", quality=9, pixelformat="yuv420p", macro_block_size=16)
    for f in frames:
        w.append_data(f)
    w.close()


BUDGET_S = float(CFG.get("time_budget_s", 8 * 3600))
Q = queue.Queue()
for j in JOBS:
    Q.put(j)
DURATIONS = []


def worker(i, pipe):
    dev = f"cuda:{i}"
    while True:
        try:
            job = Q.get_nowait()
        except queue.Empty:
            return
        left = BUDGET_S - (time.time() - T0)
        need = 1.3 * (sum(DURATIONS) / len(DURATIONS)) if DURATIONS else 0
        if left < need:
            record({"job_id": job["job_id"], "item": job["item"], "ok": False, "skipped": True,
                    "error": f"time budget: {left:.0f}s left, a job takes ~{need / 1.3:.0f}s"})
            continue
        t = time.time()
        row = {"job_id": job["job_id"], "item": job["item"], "gpu": i, "gpu_name": torch.cuda.get_device_name(i)}
        try:
            log(f"gpu{i}: {job['item']} start ({job['width']}x{job['height']}x{job['frames']}, {job['steps']} steps)")
            frames, used, notes = run_job(pipe, i, job)
            path = os.path.join(WORK, f"{job['job_id']}.mp4")
            save(frames, path, job["fps"])
            mean = float(frames.mean()) / 255
            row.update(ok=True, file=os.path.basename(path), params=used, notes=notes,
                       mean_level=round(mean, 3), n_frames=int(len(frames)))
            if mean < 0.02:
                row.update(ok=False, error="frames are black (likely fp16 overflow)")
        except Exception as exc:  # noqa: BLE001 - one shot never kills the batch
            row.update(ok=False, error=f"{type(exc).__name__}: {exc}", trace=traceback.format_exc()[-1500:])
            torch.cuda.empty_cache()
        row["seconds"] = round(time.time() - t, 1)
        row["peak_vram_gb"] = round(torch.cuda.max_memory_allocated(dev) / 1e9, 2)
        if row.get("ok"):
            DURATIONS.append(row["seconds"])
        record(row)
        log(f"gpu{i}: {job['item']} {'ok' if row.get('ok') else 'FAILED: ' + row.get('error', '')} in {row['seconds']}s")


write_json("status.json", {"phase": "loading", "jobs_sha": SHA})
workers = []
for i in range(min(NGPU, len(JOBS))):
    t = time.time()
    try:
        pipe = load_pipe(i)
    except Exception as exc:  # noqa: BLE001
        log(f"gpu{i}: load failed: {exc}")
        if i == 0:
            for j in JOBS:
                record({"job_id": j["job_id"], "item": j["item"], "ok": False,
                        "error": f"pipeline load failed: {type(exc).__name__}: {exc}",
                        "trace": traceback.format_exc()[-1500:]})
            raise
        break
    log(f"gpu{i}: pipeline loaded in {time.time() - t:.0f}s, {torch.cuda.memory_allocated(i) / 1e9:.1f} GB")
    th = threading.Thread(target=worker, args=(i, pipe), daemon=True)
    th.start()
    workers.append(th)
write_json("status.json", {"phase": "running", "jobs_sha": SHA, "workers": len(workers)})
for th in workers:
    th.join()
write_json("status.json", {"phase": "done", "jobs_sha": SHA, "seconds": round(time.time() - T0, 1)})
log("done")
