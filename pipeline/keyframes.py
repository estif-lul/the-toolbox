"""Reference sheets (`make refs`) and keyframes (`make keyframes`).

**Refs** lock the look before any shot is drawn:
- `style`: a neutral scene in the style block (the red toolbox on a table). The chosen image is
  passed to every later image as the style reference, and it also shows the toolbox.
- one sheet per character: full figure, front view, plain background, the character's fixed
  description; the chosen style image is a reference.
- the age chain: a character with `derived_from` (dad_now, me_teen, me_adult) is drawn *from its
  parent's chosen sheet* ("the same person, older"), so faces stay related across ages.
An item is generated only when everything it depends on has been chosen; `make refs` makes
whatever is ready and says what is waiting for a choice. Choices are indexes in storyboard.json
(`style.reference_choice`, `characters[].reference_choice`), never paths.

**Keyframes**: 3 candidates per shot (and per split-screen layer: s10a, s10b), seeds `seed`,
+1, +2, at 1024x1024. References: the chosen sheets of the characters in the shot, then the
style image (at most 4, the model's limit). The prompt is

    {image_prompt}. {character descriptions}. {prop descriptions}. {composition}. Style: {style block}
    + one sentence naming what each reference image is.

Each shot gets a contact sheet with the 9:16 and 16:9 crops drawn on every candidate, so the
choice (`keyframe_choice`) is made on what each export will really show.

Caching: a candidate's key holds the model, steps, size, seed, the exact prompt and the bytes
of every reference image. Changing a prompt regenerates that shot only; choosing a different
character sheet regenerates the shots that use the character. FLUX.2 klein does not reproduce an
image from its seed (FAILURES.md F07), so the committed files are what makes a run reproducible.
If klein is unavailable, the chain falls back to FLUX.1 schnell, text only (logged).
"""

from __future__ import annotations

import io
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import cache
from .common import storyboard as sbm
from .common.cache import (Manifest, artifact_path, atomic_write_bytes, cache_key, file_sha256, rel,
                           sha256_text)
from .common.crops import export_crop
from .common.env import ROOT
from .common.invoke import AllProvidersFailed, invoke
from .common.log import log_event, read_log
from .providers import registry

REFS, KEYFRAMES = "refs", "keyframes"
REFS_VERSION = KEYFRAMES_VERSION = 1
REF_CANDIDATES, KEYFRAME_CANDIDATES = 4, 3
SIZE = 1024
STYLE_SEED = 1001
WORKERS = 4
# Workers AI neurons per 1024x1024 image (COSTS.md, from the documented per-tile rates)
NEURONS = {"klein": 104.2, "klein_ref": 21.5, "schnell": 57.6}
NEURONS_PER_DAY = 10_000
BUDGET_MARGIN = int(os.environ.get("NEURON_MARGIN", 300))  # our count is an estimate from documented
                                                           # rates: keep a margin (env NEURON_MARGIN)

SHEET = ("Character reference sheet: a full-body view of {desc}. Standing in a relaxed, neutral pose, "
         "facing the viewer, the whole figure visible from head to feet, centred on a plain light "
         "warm-grey background, nothing else in the picture")
STYLE_SCENE = ("A quiet still life: {toolbox}, standing closed on a simple wooden table in a sunlit room, "
               "a window with soft morning light behind it")


class NotReady(RuntimeError):
    pass


@dataclass
class Job:
    stage: str
    item: str                 # "style", "dad", "s05", "s10a"
    index: int                # candidate number
    seed: int
    text: str                 # the prompt without the reference sentence
    refs: list[tuple[str, Path]] = field(default_factory=list)  # (what it shows, file)
    ref_note: str | None = None   # replaces the default "keep each person..." sentence
    priority: int = 99            # lower runs first (keyframes: the shot's GPU priority)

    @property
    def cand_id(self) -> str:
        return f"{self.item}#{self.index}"

    def prompt(self, with_refs: bool) -> str:
        if not (with_refs and self.refs):
            return self.text
        parts = [f"image {i} is {what}" for i, (what, _) in enumerate(self.refs, 1)]
        has_style = any("style reference" in what for what, _ in self.refs)
        people = any("style reference" not in what for what, _ in self.refs)
        default = " ".join(filter(None, [
            "Keep each person's face, skin tone, hair and clothes exactly as in their reference." if people else "",
            "Match the line work, palette and texture of the style reference." if has_style
            else "Keep the art style of the references."]))
        note = self.ref_note or default
        return f"{self.text}. Reference images: {'; '.join(parts)}. {note}"


# ---------------------------------------------------------------------------------------------
# storyboard helpers

def label(description: str) -> str:
    """'the father: a Habesha …' -> 'the father'."""
    return description.split(":", 1)[0].strip() if ":" in description else description.split(",")[0]


def _by_id(items: list[dict]) -> dict[str, dict]:
    return {x["id"]: x for x in items or []}


def describe(sb: dict, characters: list[str], props: list[str]) -> str:
    chars, prs = _by_id(sb.get("characters")), _by_id(sb.get("props"))
    texts = [chars[c]["description"] for c in characters] + [prs[p]["description"] for p in props]
    return ". ".join(x[0].upper() + x[1:] for x in texts)


def compose(sb: dict, image_prompt: str, characters: list[str], props: list[str]) -> str:
    style = sb["style"]
    parts = [image_prompt.rstrip(". "), describe(sb, characters, props), style.get("composition", ""),
             f"Style: {style['block']}"]
    return ". ".join(p[0].upper() + p[1:] for p in parts if p)


def chosen(stage: str, item: str, choice: int | None, manifest: Manifest | None = None) -> Path | None:
    """The file of the chosen candidate of `item`, or None while undecided."""
    if choice is None:
        return None
    entry = (manifest or Manifest(stage)).get(f"{item}#{choice}")
    if not entry or not (ROOT / entry["path"]).exists():
        raise NotReady(f"{item}: candidate #{choice} is chosen but {stage} has no such file; run `make {stage}`")
    return ROOT / entry["path"]


def style_ref(sb: dict, manifest: Manifest | None = None) -> Path | None:
    return chosen(REFS, "style", sb["style"].get("reference_choice"), manifest)


# ---------------------------------------------------------------------------------------------
# jobs

def ref_jobs(sb: dict, items: list[str] | None = None, force_all: bool = False) -> tuple[list[Job], list[str]]:
    """Candidate jobs for every ref item whose dependencies are chosen, and the items waiting.
    An item that already has a choice is locked (no jobs) unless `force_all`: changing an
    upstream sheet never regenerates a chosen one by surprise."""
    manifest = Manifest(REFS)
    jobs, waiting = [], []
    want = set(items) if items else None
    toolbox = _by_id(sb.get("props")).get("toolbox", {}).get("description", "a red metal toolbox")
    if (not want or "style" in want) and (sb["style"].get("reference_choice") is None or force_all):
        text = compose(sb, STYLE_SCENE.format(toolbox=toolbox), [], [])
        jobs += [Job(REFS, "style", i, STYLE_SEED + i, text) for i in range(REF_CANDIDATES)]
    style = style_ref(sb, manifest)
    chars = _by_id(sb.get("characters"))
    for cid, ch in chars.items():
        if want and cid not in want:
            continue
        if ch.get("reference_choice") is not None and not force_all:
            chosen(REFS, cid, ch["reference_choice"], manifest)  # locked: only check the file exists
            continue
        if style is None:
            waiting.append(f"{cid} (needs style.reference_choice)")
            continue
        refs: list[tuple[str, Path]] = []
        parent = ch.get("derived_from")
        if parent:
            pfile = chosen(REFS, parent, chars[parent].get("reference_choice"), manifest)
            if pfile is None:
                waiting.append(f"{cid} (needs {parent}.reference_choice)")
                continue
            refs.append((f"{label(chars[parent]['description'])}, the same person at a younger age", pfile))
        else:
            # Only root sheets get the style image: a parent sheet already carries the style, and
            # the style image's own subject (table, toolbox) leaked into 2 of 4 Dad sheets.
            refs.append(("the style reference (ignore its subject)", style))
        text = ". ".join([SHEET.format(desc=ch["description"]), f"Style: {sb['style']['block']}"])
        # An age jump: keep the family resemblance, not the body or the clothes (the first teen
        # sheets copied the child's proportions and drew "a faint moustache" as a full one).
        note = (f"Keep the family resemblance to reference image 1 (face shape, eyes, skin tone, hair "
                f"texture) and its art style, but draw him at the new age, with the body proportions and "
                f"clothes described above") if parent else None
        jobs += [Job(REFS, cid, i, int(ch["seed"]) + i, text, refs, note) for i in range(REF_CANDIDATES)]
    return jobs, waiting


def keyframe_items(sb: dict) -> list[dict]:
    """One entry per image to draw: plain shots, and each layer of a split-screen shot."""
    out = []
    for shot in sb["shots"]:
        for layer in shot.get("layers") or []:
            out.append({"id": f"{shot['id']}{layer['id']}", "shot": shot["id"], "layer": layer["id"],
                        "image_prompt": layer["image_prompt"], "characters": layer.get("characters") or [],
                        "props": layer.get("props") or [], "seed": layer["seed"],
                        "choice": layer.get("keyframe_choice"),
                        "crop_focus": layer.get("crop_focus") or shot.get("crop_focus"), "half": True})
        if not shot.get("layers"):
            out.append({"id": shot["id"], "shot": shot["id"], "layer": None, "image_prompt": shot["image_prompt"],
                        "characters": shot.get("characters") or [], "props": shot.get("props") or [],
                        "seed": shot["seed"], "choice": shot.get("keyframe_choice"),
                        "crop_focus": shot.get("crop_focus"), "half": False})
    return out


def keyframe_jobs(sb: dict, only: list[str] | None = None) -> list[Job]:
    manifest = Manifest(REFS)
    style = style_ref(sb, manifest)
    if style is None:
        raise NotReady("choose the style reference first (style.reference_choice), then the character sheets")
    chars = _by_id(sb.get("characters"))
    jobs = []
    for it in keyframe_items(sb):
        if only and it["id"] not in only and it["shot"] not in only:
            continue
        refs = []
        for c in it["characters"]:
            f = chosen(REFS, c, chars[c].get("reference_choice"), manifest)
            if f is None:
                raise NotReady(f"{it['id']}: choose a reference sheet for {c} first ({c}.reference_choice)")
            refs.append((label(chars[c]["description"]), f))
        if not refs or "toolbox" in it["props"] or "toolbox_old" in it["props"]:
            # Character sheets already carry the style; the style image (the toolbox on a table)
            # is added only where nothing else carries the look, or where the toolbox is in shot.
            refs.append(("the style reference, which also shows the red toolbox", style))
        refs = refs[:4]
        text = compose(sb, it["image_prompt"], it["characters"], it["props"])
        prio = int(next(s for s in sb["shots"] if s["id"] == it["shot"]).get("priority") or 99)
        jobs += [Job(KEYFRAMES, it["id"], i, int(it["seed"]) + i, text, refs, priority=prio)
                 for i in range(KEYFRAME_CANDIDATES)]
    return jobs


REVISE = ("Edit reference image 1: {instruction}. Keep everything else exactly as it is: the same "
          "person, face, skin tone, hair, beard, clothes, pose, background, framing and art style")
REVISIONS = 2


def revise_jobs(sb: dict, item: str, from_index: int, instruction: str, n: int = REVISIONS) -> list[Job]:
    """`n` edits of candidate `item#from_index`, numbered after the existing candidates."""
    manifest = Manifest(REFS)
    src = chosen(REFS, item, from_index, manifest)
    first = max([int(k.split("#")[1]) for k in manifest.entries if k.split("#")[0] == item] + [-1]) + 1
    chars = _by_id(sb.get("characters"))
    base_seed = int(chars[item]["seed"]) if item in chars else STYLE_SEED
    text = REVISE.format(instruction=instruction.rstrip(". "))
    return [Job(REFS, item, first + k, base_seed + 100 + k, text, [("the sheet to edit", src)]) for k in range(n)]


def run_revise(item: str, from_index: int, instruction: str, profile: str | None = None, *, dry_run: bool = False,
               sb: dict | None = None, chain: Any = None, console: Any = None) -> dict:
    from rich.console import Console

    console = console or Console()
    sb = sb if sb is not None else sbm.load_storyboard()
    jobs = revise_jobs(sb, item, from_index, instruction)
    res = run_jobs(jobs, profile=profile, dry_run=dry_run, chain=chain, console=console)
    if not dry_run:
        manifest = Manifest(REFS)
        for j in jobs:  # provenance: what each revision was made from, and how
            e = manifest.get(j.cand_id)
            if e:
                manifest.put(j.cand_id, **{**{k: v for k, v in e.items() if k not in ("created_at", "sha256")},
                                           "revised_from": f"{item}#{from_index}", "instruction": instruction})
        n = max(int(k.split("#")[1]) for k in manifest.entries if k.split("#")[0] == item) + 1
        out = contact_sheet(item, REFS, n, cache.OUTPUTS / REFS / f"contact_{item}.png",
                            title=f"{item}: reference candidates (#{jobs[0].index}+ = edits of #{from_index})")
        made = [j.cand_id for j in jobs if manifest.get(j.cand_id)]
        console.print(f"  contact sheet: {rel(out)}  (new: {', '.join(made) or 'none'})")
    return res


# ---------------------------------------------------------------------------------------------
# running

def job_key(job: Job, provider: Any) -> str:
    uses_refs = bool(job.refs) and getattr(provider, "max_refs", 0) > 0
    return cache_key(stage=job.stage, stage_version=REFS_VERSION if job.stage == REFS else KEYFRAMES_VERSION,
                     provider=provider.name, model=provider.model,
                     params={"steps": provider.params.get("steps"), "w": SIZE, "h": SIZE}, seed=job.seed,
                     inputs={"prompt": job.prompt(uses_refs)},
                     upstream_hashes={f"ref{i}": file_sha256(p) for i, (_, p) in enumerate(job.refs)} if uses_refs else {})


def neurons(model: str, n_refs: int) -> float:
    if "schnell" in model:
        return NEURONS["schnell"]
    return NEURONS["klein"] + NEURONS["klein_ref"] * n_refs


def neurons_today(log_path: Path | None = None) -> float:
    """Estimated Workers AI neurons used since 00:00 UTC (the free allowance's reset)."""
    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total = 0.0
    for r in read_log(log_path):
        if (r.get("event") == "model_call" and r.get("provider") == "cloudflare_image" and r.get("status") == "ok"
                and datetime.fromisoformat(r["ts"]) >= since):
            total += neurons(r.get("model") or "", int((r.get("params") or {}).get("refs") or 0))
    return total


def _hit(job: Job, providers: list[Any], manifest: Manifest) -> dict | None:
    for p in providers:  # a candidate from any model in the chain stays until forced
        if manifest.is_fresh(job.cand_id, job_key(job, p)):
            return manifest.get(job.cand_id)
    return None


def run_jobs(jobs: list[Job], *, profile: str | None = None, force: list[str] | None = None, dry_run: bool = False,
             chain: Any = None, console: Any = None) -> dict:
    from rich.console import Console

    console = console or Console()
    if not jobs:
        return {"generated": 0, "hits": 0}
    stage = jobs[0].stage
    chain = chain if chain is not None else registry.get_provider("image", profile)
    providers = list(getattr(chain, "providers", chain))
    manifest = Manifest(stage)
    todo, hits = [], 0
    for job in jobs:
        forced = force is not None and (not force or job.item in force or job.cand_id in force
                                        or any(job.item.startswith(f) for f in force))
        entry = None if forced else _hit(job, providers, manifest)
        if entry:
            hits += 1
            log_event("cache_hit", stage=stage, shot_id=job.cand_id, provider=entry["provider"], model=entry["model"],
                      cache_key=entry["cache_key"], output=entry["path"], seed=job.seed)
        else:
            todo.append(job)
    todo.sort(key=lambda j: (j.priority, j.item, j.index))
    used = neurons_today()
    room = NEURONS_PER_DAY - BUDGET_MARGIN - used
    deferred, kept, need = [], [], 0.0
    for j in todo:  # whole items only: a shot with 1 of 3 candidates is no help
        cost = neurons(providers[0].model, len(j.refs))
        if deferred and deferred[-1].item == j.item or need + cost > room:
            deferred.append(j)
        else:
            kept.append(j)
            need += cost
    whole = {j.item for j in deferred}
    deferred += [j for j in kept if j.item in whole]
    kept = [j for j in kept if j.item not in whole]
    need = sum(neurons(providers[0].model, len(j.refs)) for j in kept)
    if deferred:
        console.print(f"[yellow]daily allowance: deferring {len(deferred)} candidate(s) of "
                      f"{', '.join(sorted(whole))} until it resets (03:00 EAT); run again then[/yellow]")
    todo = kept
    console.print(f"{stage}: {len(jobs)} candidates, {hits} cache hit(s), {len(todo)} to generate "
                  f"(~{need:.0f} neurons; ~{used:.0f} of {NEURONS_PER_DAY} used today by runs.jsonl's count, "
                  f"resets 03:00 EAT)")
    if dry_run or not todo:
        return {"generated": 0, "hits": hits, "neurons": need}

    def one(job: Job):
        def call(p):
            uses = bool(job.refs) and p.max_refs > 0
            return p.generate(job.prompt(uses), job.seed, SIZE, SIZE, refs=[f for _, f in job.refs] if uses else [])

        def save(p, key, result):
            path = artifact_path(stage, job.item, key, "jpg" if "jpeg" in result.mime else "png")
            atomic_write_bytes(path, result.data)
            return path

        r = invoke(providers, call, stage=stage, shot_id=job.cand_id, seed=job.seed,
                   params={"refs": len(job.refs), "ref_files": [rel(f) for _, f in job.refs]},
                   input_hash=sha256_text(job.text), key_fn=lambda p: job_key(job, p), save=save, max_attempts=2)
        return job, r

    done, failed = [], []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for fut in [pool.submit(one, j) for j in todo]:
            try:
                done.append(fut.result())
            except AllProvidersFailed as exc:
                failed.append(str(exc))
    for job, r in done:  # manifest writes stay on one thread
        manifest.put(job.cand_id, cache_key=r.cache_key, path=r.output, provider=r.provider.name,
                     model=r.provider.model, seed=job.seed, fell_back=r.fell_back,
                     refs=[rel(f) for _, f in job.refs] if r.provider.max_refs else [],
                     prompt_sha=sha256_text(job.prompt(bool(r.provider.max_refs))))
    for msg in failed:
        console.print(f"[red]{msg}[/red]")
    return {"generated": len(done), "hits": hits, "failed": len(failed), "neurons": need}


# ---------------------------------------------------------------------------------------------
# contact sheets

def _font(size: int):
    from PIL import ImageFont

    for name in ("assets/fonts/AtkinsonHyperlegible-Regular.ttf", "C:/Windows/Fonts/arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        try:
            return ImageFont.truetype(str(ROOT / name) if not Path(name).is_absolute() else name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def contact_sheet(item: str, stage: str, n: int, out: Path, *, crops: dict | None = None, title: str = "",
                  thumb: int = 420) -> Path | None:
    """Candidates side by side, labelled #index / seed / model; crop boxes drawn if given
    ({'9x16': (x, y, w, h), '16x9': ...} in master pixels)."""
    from PIL import Image, ImageDraw

    manifest = Manifest(stage)
    cands = [(i, manifest.get(f"{item}#{i}")) for i in range(n)]
    cands = [(i, e) for i, e in cands if e and (ROOT / e["path"]).exists()]
    if not cands:
        return None
    pad, head, foot = 12, 36 if title else 0, 30
    sheet = Image.new("RGB", (pad + len(cands) * (thumb + pad), head + thumb + foot + pad), (245, 241, 234))
    draw = ImageDraw.Draw(sheet)
    font, small = _font(20), _font(16)
    if title:
        draw.text((pad, 8), title, fill=(40, 34, 28), font=font)
    colours = {"9x16": (230, 120, 20), "16x9": (20, 150, 200)}
    for k, (i, e) in enumerate(cands):
        with Image.open(ROOT / e["path"]) as im:
            im = im.convert("RGB")
            scale = thumb / im.width
            t = im.resize((thumb, round(im.height * scale)))
        x0, y0 = pad + k * (thumb + pad), head
        sheet.paste(t, (x0, y0))
        for name, (cx, cy, cw, ch) in (crops or {}).items():
            box = [x0 + cx * scale, y0 + cy * scale, x0 + (cx + cw) * scale - 1, y0 + (cy + ch) * scale - 1]
            draw.rectangle(box, outline=colours.get(name, (255, 0, 0)), width=3)
        model = e["model"].split("/")[-1]
        draw.text((x0, y0 + t.height + 6), f"#{i}  seed {e.get('seed')}  {model}"
                  + ("  (fallback)" if e.get("fell_back") else ""), fill=(40, 34, 28), font=small)
    if crops:
        draw.text((sheet.width - 330, 8), "orange = 9:16   blue = 16:9", fill=(40, 34, 28), font=small)
    buf = io.BytesIO()
    sheet.save(buf, "PNG", optimize=True)
    atomic_write_bytes(out, buf.getvalue())
    return out


# ---------------------------------------------------------------------------------------------
# stage entry points

def run_refs(profile: str | None = None, *, only: list[str] | None = None, force: list[str] | None = None,
             dry_run: bool = False, sb: dict | None = None, chain: Any = None, console: Any = None) -> dict:
    from rich.console import Console

    console = console or Console()
    sb = sb if sb is not None else sbm.load_storyboard()
    report = sbm.validate(sb)
    if not report.ok:
        raise NotReady("storyboard.json is invalid:\n  " + "\n  ".join(report.errors))
    jobs, waiting = ref_jobs(sb, only, force_all=force is not None)
    res = run_jobs(jobs, profile=profile, force=force, dry_run=dry_run, chain=chain, console=console)
    sheets = []
    for item in sorted({j.item for j in jobs}, key=[j.item for j in jobs].index):
        if not dry_run:
            out = contact_sheet(item, REFS, REF_CANDIDATES, cache.OUTPUTS / REFS / f"contact_{item}.png",
                                title=f"{item}: reference candidates")
            if out:
                sheets.append(rel(out))
    for s in sheets:
        console.print(f"  contact sheet: {s}")
    for w in waiting:
        console.print(f"  [yellow]waiting:[/yellow] {w}")
    return {**res, "sheets": sheets, "waiting": waiting}


def run_keyframes(profile: str | None = None, *, only: list[str] | None = None, force: list[str] | None = None,
                  dry_run: bool = False, sb: dict | None = None, chain: Any = None, console: Any = None) -> dict:
    from rich.console import Console

    console = console or Console()
    sb = sb if sb is not None else sbm.load_storyboard()
    report = sbm.validate(sb)
    if not report.ok:
        raise NotReady("storyboard.json is invalid:\n  " + "\n  ".join(report.errors))
    jobs = keyframe_jobs(sb, only)
    res = run_jobs(jobs, profile=profile, force=force, dry_run=dry_run, chain=chain, console=console)
    sheets = []
    if not dry_run:
        for it in keyframe_items(sb):
            if only and it["id"] not in only and it["shot"] not in only:
                continue
            crops = {name: export_crop(name, it["crop_focus"], half=it["half"]) for name in ("9x16", "16x9")}
            out = contact_sheet(it["id"], KEYFRAMES, KEYFRAME_CANDIDATES,
                                cache.OUTPUTS / KEYFRAMES / it["id"] / "contact.png", crops=crops,
                                title=f"{it['id']}: keyframe candidates" + (" (split-screen half)" if it["half"] else ""))
            if out:
                sheets.append(rel(out))
        console.print(f"  {len(sheets)} contact sheet(s): outputs/keyframes/<shot>/contact.png")
    return {**res, "sheets": sheets}


def rebuild_sheets(sb: dict | None = None) -> list[str]:
    """Every contact sheet again from the manifests (no model calls): refs and keyframes."""
    sb = sb if sb is not None else sbm.load_storyboard()
    out = []
    refs = Manifest(REFS)
    for item in ["style", *[c["id"] for c in sb.get("characters") or []]]:
        idx = [int(key.split("#")[1]) for key in refs.entries if key.split("#")[0] == item]
        if not idx:
            continue
        revised = sorted({refs.entries[f"{item}#{i}"].get("revised_from") for i in idx} - {None})
        title = f"{item}: reference candidates" + (f" (#{REF_CANDIDATES}+ = edits of {', '.join(revised)})"
                                                   if revised else "")
        p = contact_sheet(item, REFS, max(idx) + 1, cache.OUTPUTS / REFS / f"contact_{item}.png", title=title)
        out.append(rel(p))
    for it in keyframe_items(sb):
        crops = {name: export_crop(name, it["crop_focus"], half=it["half"]) for name in ("9x16", "16x9")}
        p = contact_sheet(it["id"], KEYFRAMES, KEYFRAME_CANDIDATES, cache.OUTPUTS / KEYFRAMES / it["id"] / "contact.png",
                          crops=crops, title=f"{it['id']}: keyframe candidates" + (" (split-screen half)" if it["half"] else ""))
        if p:
            out.append(rel(p))
    return out
