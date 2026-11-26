"""Moving shots. Step 3 builds the **Ken Burns** clips (`make kenburns`), the fallback that exists for
every shot: the chosen keyframe, upscaled, with a slow eased push / pull / pan from the storyboard
(`kenburns.move`, `kenburns.amount`), rendered at the master size (1024x1024, 24 fps) for exactly
the shot's measured duration. A split-screen shot gets one clip per layer (s10a, s10b).

Cached like a model call: the key holds the keyframe's bytes, the move, the amount and the duration,
so a new keyframe choice or a narration change that alters the shot's length re-renders only
that shot. Each render is logged as a `kenburns` provider call (latency, zero cost).
The Wan 2.2 moving shots (Step 4) are added to this file.
"""

from __future__ import annotations

from typing import Any

from .common import storyboard as sbm
from .common.cache import Manifest, artifact_path, cache_key, file_sha256, rel
from .common.log import log_event, timed_call
from .keyframes import KEYFRAMES, chosen, keyframe_items
from .providers import registry

STAGE = "kenburns"
STAGE_VERSION = 1


def kb_plan(sb: dict, tl: dict) -> tuple[list[dict], list[str]]:
    """(renderable items with their keyframe file and duration, items waiting for a keyframe)."""
    shots = {s["id"]: s for s in sb["shots"]}
    durations = {s["shot_id"]: s["duration_s"] for s in tl["shots"]}
    manifest = Manifest(KEYFRAMES)
    items, waiting = [], []
    for it in keyframe_items(sb):
        f = chosen(KEYFRAMES, it["id"], it["choice"], manifest)
        if f is None:
            waiting.append(it["id"])
            continue
        kb = shots[it["shot"]].get("kenburns") or {"move": "static", "amount": 0.0}
        items.append({**it, "file": f, "duration_s": durations[it["shot"]], "move": kb["move"],
                      "amount": float(kb.get("amount", 0.0))})
    return items, waiting


def run_kenburns(profile: str | None = None, *, only: list[str] | None = None, force: list[str] | None = None,
                 dry_run: bool = False, sb: dict | None = None, console: Any = None) -> dict:
    from rich.console import Console

    console = console or Console()
    sb = sb if sb is not None else sbm.load_storyboard()
    timing = sbm.load_timing()
    tl = sbm.timeline(sb, timing)
    kb = registry.get_provider(STAGE, profile).primary
    fps, size = int(kb.params.get("fps", 24)), int(kb.params.get("size", 1024))
    items, waiting = kb_plan(sb, tl)
    manifest = Manifest(STAGE)
    made = hits = 0
    for it in items:
        if only and it["id"] not in only and it["shot"] not in only:
            continue
        params = {"move": it["move"], "amount": it["amount"], "fps": fps, "size": size}
        key = cache_key(stage=STAGE, stage_version=STAGE_VERSION, provider=kb.name, model=kb.model, params=params,
                        inputs={"duration_s": round(it["duration_s"], 3)},
                        upstream_hashes={"keyframe": file_sha256(it["file"])})
        forced = force is not None and (not force or it["id"] in force or it["shot"] in force)
        if not forced and manifest.is_fresh(it["id"], key):
            hits += 1
            log_event("cache_hit", stage=STAGE, shot_id=it["id"], provider=kb.name, model=kb.model, cache_key=key,
                      output=manifest.get(it["id"])["path"])
            continue
        out = artifact_path(STAGE, it["id"], key, "mp4")
        with timed_call(stage=STAGE, provider=kb.name, model=kb.model, shot_id=it["id"], params=params,
                        cache_key=key) as rec:
            kb.render(it["file"], out, duration_s=it["duration_s"], move=it["move"], amount=it["amount"],
                      fps=fps, size=size, dry_run=dry_run)
            rec.output = out
        if not dry_run:
            manifest.put(it["id"], cache_key=key, path=out, provider=kb.name, model=kb.model,
                         keyframe=rel(it["file"]), duration_s=it["duration_s"], **params)
        made += 1
    console.print(f"kenburns: {made} rendered, {hits} cache hit(s)"
                  + (f"; waiting for a keyframe choice: {', '.join(waiting)}" if waiting else ""))
    return {"rendered": made, "hits": hits, "waiting": waiting}


# ---- Wan 2.2 moving shots (Step 4) ---------------------------------------------------------------
# The Wan jobs read the chosen keyframes. A clip is cached like any model output: the key holds the
# keyframe's bytes, the motion prompt, the negative prompt, the seed and the generation params, so a
# new keyframe or motion prompt re-queues only that shot. The work runs on Kaggle (batch-async):
# `make shots-push` sends the stale jobs, `make shots-pull` ingests what finished.

WAN_STAGE = "shots"
WAN_VERSION = 1
STYLE_SUFFIX = "Hand-painted 2D storybook cartoon, soft golden light, gentle natural motion"
MOTION_NEGATIVE = ("flicker, morphing, warping, melting, extra limbs, extra fingers, distorted hands, "
                   "sudden cuts, fast camera movement, camera shake, blurry, static image")
WAN_PARAMS = ("width", "height", "frames", "steps", "guidance", "fps")


def wan_prompt(motion: str) -> str:
    return f"{motion.rstrip('. ')}. {STYLE_SUFFIX}."


def wan_jobs(sb: dict, model: str, params: dict, provider: str = "kaggle_wan") -> tuple[list[dict], list[str]]:
    """Every image of a `motion: wan` shot with a chosen keyframe -> a job with its cache key.
    Returns (jobs sorted by priority, items still waiting for a keyframe choice)."""
    shots = {s["id"]: s for s in sb["shots"]}
    negative = f"{(sb.get('style') or {}).get('negative', '')}, {MOTION_NEGATIVE}".strip(", ")
    p = {k: params[k] for k in WAN_PARAMS if k in params}
    p.setdefault("fps", 24)
    manifest = Manifest(KEYFRAMES)
    jobs, waiting = [], []
    for it in keyframe_items(sb):
        shot = shots[it["shot"]]
        if shot.get("motion") != "wan":
            continue
        layer = next((lay for lay in shot.get("layers") or [] if lay["id"] == it["layer"]), None)
        motion = (layer or {}).get("motion_prompt") or shot.get("motion_prompt")
        f = chosen(KEYFRAMES, it["id"], it["choice"], manifest)
        if f is None or not motion:
            waiting.append(it["id"])
            continue
        prompt, seed = wan_prompt(motion), int(it["seed"])
        key = cache_key(stage=WAN_STAGE, stage_version=WAN_VERSION, provider=provider, model=model, params=p,
                        seed=seed, inputs={"prompt": prompt, "negative_prompt": negative},
                        upstream_hashes={"keyframe": file_sha256(f)})
        jobs.append({"job_id": key[:16], "cache_key": key, "item": it["id"], "shot": it["shot"],
                     "priority": int(shot.get("priority", 99)), "keyframe": f, "prompt": prompt,
                     "negative_prompt": negative, "seed": seed, "params": p})
    jobs.sort(key=lambda j: (j["priority"], j["item"]))
    return jobs, waiting


def _media_jobs(jobs: list[dict]):
    from .providers.base import MediaJob

    return [MediaJob(job_id=j["job_id"], shot_id=j["item"], prompt=j["prompt"], seed=j["seed"],
                     params={**j["params"], "priority": j["priority"]}, image_path=j.get("keyframe"),
                     negative_prompt=j.get("negative_prompt")) for j in jobs]


def stale_jobs(jobs: list[dict], manifest: Manifest, only=None, force=None) -> list[dict]:
    out = []
    for j in jobs:
        if only and j["item"] not in only and j.get("shot") not in only:
            continue
        forced = force is not None and (not force or j["item"] in force or j.get("shot") in force)
        if forced or not manifest.is_fresh(j["item"], j["cache_key"]):
            out.append(j)
    return out


def ingest(results, handle: dict, manifest: Manifest, *, stage: str, provider: str, model: str) -> dict:
    """Copy finished outputs into the cache, update the manifest, log one model_call per job.
    A job already ingested (same key, fresh) is skipped, so pulling twice logs nothing twice."""
    import shutil

    by_id = {j["job_id"]: j for j in handle["jobs"]}
    done, failed, unknown = [], [], []
    for r in results:
        job = by_id.get(r.job_id)
        if job is None:
            unknown.append(r.job_id)
            continue
        item, key = job["item"], job["cache_key"]
        if manifest.is_fresh(item, key):
            continue
        row = r.meta or {}
        out = None
        if r.ok and r.path is not None:
            out = artifact_path(stage, item, key, r.path.suffix.lstrip("."))
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(r.path, out)
            used = row.get("params") or row.get("params_used") or {}
            degraded = any(k in used and used[k] != job["params"].get(k) for k in ("width", "height", "frames"))
            manifest.put(item, cache_key=key, path=out, provider=provider, model=model, seed=job.get("seed"),
                         seconds=r.seconds, gpu=row.get("gpu_name"), params_used=used, degraded=degraded,
                         notes=row.get("notes") or [], jobs_sha=handle["jobs_sha"])
            done.append(item)
        else:
            failed.append(f"{item}: {r.error}")
        log_event("model_call", stage=stage, shot_id=item, provider=provider, model=model,
                  params=job["params"], seed=job.get("seed"), cache_key=key, output=out,
                  latency_s=r.seconds, gpu_s=r.seconds, cost_usd=0.0,
                  status="ok" if out else "error", error=None if out else str(r.error or "failed")[:400])
    return {"ingested": done, "failed": failed, "unknown": unknown}


def keep_evidence(folder, stage_dir, jobs_sha: str) -> None:
    """Copy the small text outputs of a Kaggle run (results, env, log) next to the clips."""
    from .common.cache import atomic_write_text
    from .providers.kaggle_common import scrub

    dst = stage_dir / "kaggle" / jobs_sha[:12]
    dst.mkdir(parents=True, exist_ok=True)
    for f in folder.iterdir():
        if f.is_file() and f.suffix in (".jsonl", ".json", ".log", ".txt") and f.stat().st_size < 5_000_000:
            atomic_write_text(dst / f.name, scrub(f.read_text(encoding="utf-8", errors="replace")))


def kaggle_round(adapter, jobs: list[dict], stage_dir, manifest: Manifest, *, stage: str, push: bool, pull: bool,
                 extra: dict | None = None, dry_run: bool = False, say=print) -> dict:
    """Shared by shots and music: push the given stale jobs, and/or wait + pull + ingest."""
    from dataclasses import asdict

    from .providers import kaggle_common as kc

    both = not push and not pull
    res: dict = {}
    if push or both:
        if not jobs:
            say(f"{stage}: nothing to push (all fresh)")
        else:
            handle = adapter.submit(_media_jobs(jobs), extra or {}, dry_run=dry_run)
            h = asdict(handle)
            h["jobs"] = [{k: (rel(v) if k == "keyframe" else v) for k, v in j.items()} for j in jobs]
            if not dry_run:
                kc.save_handle(stage_dir, h)
            say(f"{stage}: {'staged' if dry_run else 'pushed'} {len(jobs)} job(s) "
                f"({', '.join(j['item'] for j in jobs)}); jobs.json {handle.jobs_sha[:12]}"
                + ("" if dry_run else f"; {handle.meta.get('push')}"))
            res["pushed"] = [j["item"] for j in jobs]
    if (pull or both) and not dry_run:
        handle = kc.load_handle(stage_dir)
        if handle is None:
            say(f"{stage}: no Kaggle job to pull (push first)")
            return res
        status = kc.wait(adapter.kaggle_stage, say=say) if both else adapter.status(None)
        res["status"] = status
        if status in ("queued", "running"):
            say(f"{stage}: the kernel is still {status}; pull again later")
            return res
        results, folder = adapter.collect(None)
        keep_evidence(folder, stage_dir, handle["jobs_sha"])
        summary = ingest(results, handle, manifest, stage=stage, provider=adapter.name, model=adapter.model)
        res.update(summary)
        say(f"{stage}: kernel {status}; ingested {len(summary['ingested'])}"
            + (f" ({', '.join(summary['ingested'])})" if summary["ingested"] else "")
            + (f"; failed: {'; '.join(summary['failed'])}" if summary["failed"] else ""))
    return res


def run_shots(profile: str | None = None, *, push: bool = False, pull: bool = False, only: list[str] | None = None,
              force: list[str] | None = None, limit: int | None = None, dry_run: bool = False,
              console: Any = None) -> dict:
    """push (stale jobs -> Kaggle), pull (finished clips -> cache), or both with a wait in between."""
    from rich.console import Console

    from .common.cache import OUTPUTS

    console = console or Console()
    sb = sbm.load_storyboard()
    wan = registry.get_provider("video", profile).primary
    manifest = Manifest(WAN_STAGE)
    jobs, waiting = wan_jobs(sb, wan.model, wan.params, wan.name)
    stale = stale_jobs(jobs, manifest, only, force)[: limit or None]
    res = kaggle_round(wan, stale, OUTPUTS / WAN_STAGE, manifest, stage=WAN_STAGE, push=push, pull=pull,
                       extra={"time_budget_s": float(wan.params.get("time_budget_s", 8 * 3600))},
                       dry_run=dry_run, say=console.print)
    if waiting:
        console.print(f"shots: waiting for a keyframe choice: {', '.join(waiting)}")
    return {**res, "waiting": waiting}
