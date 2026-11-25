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
