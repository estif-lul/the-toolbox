"""The music stage.

Step 2 needs only the **placeholder**: a soft code-generated pad (FFmpeg `aevalsrc`, sine
partials of a slow D - Bm - G - A progression, a gentle tremolo, low-passed, faded in and out)
for the radio cut. It is not music anyone wrote or a model made, so it needs no licence, and it is
labelled a placeholder everywhere it is used. It is also the last-resort fallback of the real
music stage (ACE-Step on Kaggle, Step 4), which is built in this file later.
"""

from __future__ import annotations

from pathlib import Path

from .common import ffmpeg
from .common.cache import Manifest, artifact_path, atomic_write_json, cache_key
from .common.log import log_event

STAGE = "music"
PLACEHOLDER = "placeholder"
PLACEHOLDER_VERSION = 1
CHORD_S = 8.0          # one chord every 8 s, crossfaded
CHORDS = (             # Hz: D major, B minor, G major, A major (the cue's key is D major)
    (73.42, 146.83, 220.00, 293.66, 369.99),
    (61.74, 123.47, 185.00, 246.94, 293.66),
    (49.00, 98.00, 146.83, 196.00, 246.94),
    (55.00, 110.00, 164.81, 220.00, 277.18),
)
AMPS = (0.035, 0.05, 0.04, 0.035, 0.025)


def pad_expr(detune: float = 1.0) -> str:
    """One channel. The chord weights (1 + cos(phase - k*pi/2)) / 4 always sum to 1."""
    period = CHORD_S * len(CHORDS)
    terms = []
    for k, chord in enumerate(CHORDS):
        tones = "+".join(f"{a}*sin(2*PI*{f * detune:.3f}*t)" for f, a in zip(chord, AMPS))
        terms.append(f"(1+cos(2*PI*t/{period}-{k}*PI/2))/4*({tones})")
    return f"({'+'.join(terms)})*(0.85+0.15*sin(2*PI*0.13*t))"


def placeholder_args(duration_s: float, out: Path) -> list[str]:
    d = round(float(duration_s), 2)
    src = f"aevalsrc=exprs='{pad_expr(1.0)}|{pad_expr(1.0025)}':s=48000:d={d}"
    af = f"lowpass=f=1800,afade=t=in:d=2,afade=t=out:st={max(d - 3, 0):.2f}:d=3"
    return ["-f", "lavfi", "-i", src, "-af", af, "-c:a", "flac", str(out)]


def placeholder(duration_s: float, *, dry_run: bool = False) -> Path:
    """The placeholder pad for `duration_s`, cached by its length (FFmpeg only, no model call)."""
    d = round(float(duration_s), 2)
    key = cache_key(stage=STAGE, stage_version=PLACEHOLDER_VERSION, provider="placeholder",
                    model="ffmpeg-aevalsrc", params={"chord_s": CHORD_S, "chords": CHORDS, "amps": AMPS},
                    inputs={"duration_s": d})
    manifest = Manifest(STAGE)
    path = artifact_path(STAGE, PLACEHOLDER, key, "flac")
    if manifest.is_fresh(PLACEHOLDER, key):
        log_event("cache_hit", stage=STAGE, shot_id=PLACEHOLDER, provider="placeholder",
                  model="ffmpeg-aevalsrc", cache_key=key, output=path)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(placeholder_args(d, path), dry_run=dry_run)
    if not dry_run:
        manifest.put(PLACEHOLDER, cache_key=key, path=path, provider="placeholder", model="ffmpeg-aevalsrc",
                     duration_s=d, note="code-generated placeholder pad, not the film's music")
    return path


# ---- ACE-Step 1.5 score candidates (Step 4) --------------------------------------------------------
# One job per seed of each cue (3 candidates, same caption), the length of the film + a 4 s tail.
# BPM and key go in their own fields, not the caption. Instrumental, DiT only (no 5Hz LM "thinking"),
# turbo model, 8 steps (the documented default for turbo). Cached like any model output.

ACE_VERSION = 1
TAIL_S = 4.0
MUSIC_LUFS = -26.0   # auditions: the candidate under the narration (-16 LUFS), ducked as in the radio cut


def keyscale(key: str) -> str:
    """'D major' -> 'D Major', 'b minor' -> 'B Minor' (ACE-Step's keyscale spelling)."""
    parts = key.split()
    return " ".join([parts[0][:1].upper() + parts[0][1:], *[p.capitalize() for p in parts[1:]]]) if parts else ""


def ace_jobs(sb: dict, total_s: float, model: str, params: dict, provider: str = "kaggle_acestep") -> list[dict]:
    p = {"steps": int(params.get("steps", 8)), "shift": float(params.get("shift", 3.0)),
         "config_path": params.get("config_path", "acestep-v15-turbo")}
    jobs = []
    for cue in (sb.get("music") or {}).get("cues") or []:
        duration = float(round(total_s + TAIL_S))
        inputs = {"caption": cue["caption"], "bpm": cue.get("bpm"), "keyscale": keyscale(cue.get("key", "")),
                  "duration_s": duration, "instrumental": bool(cue.get("instrumental", True))}
        for n, seed in enumerate(cue.get("seeds") or [], start=1):
            key = cache_key(stage=STAGE, stage_version=ACE_VERSION, provider=provider, model=model, params=p,
                            seed=int(seed), inputs=inputs)
            jobs.append({"job_id": key[:16], "cache_key": key, "item": f"{cue['id']}_c{n}", "shot": cue["id"],
                         "priority": n, "prompt": cue["caption"], "seed": int(seed),
                         "params": {**p, "bpm": inputs["bpm"], "keyscale": inputs["keyscale"],
                                    "duration_s": duration, "timesignature": "4"}})
    return jobs


def candidates(sb: dict) -> list[dict]:
    """The ingested candidates of each cue: [{item, path, seed}] in seed order."""
    manifest = Manifest(STAGE)
    out = []
    for cue in (sb.get("music") or {}).get("cues") or []:
        for n, _ in enumerate(cue.get("seeds") or [], start=1):
            e = manifest.get(f"{cue['id']}_c{n}")
            if e and e.get("status") == "ok":
                out.append({"item": f"{cue['id']}_c{n}", "n": n, "path": e["path"], "seed": e.get("seed")})
    return out


def audition(sb: dict, *, dry_run: bool = False, console=None) -> list[dict]:
    """The radio cut once per candidate -> outputs/cuts/audition_cN.mp4 (+ loudness of each candidate)."""
    from .assemble import run_radio
    from .common.cache import OUTPUTS
    from .common.env import ROOT

    out = []
    for c in candidates(sb):
        qc = run_radio(dry_run=dry_run, sb=sb, music_path=ROOT / c["path"], music_lufs=MUSIC_LUFS,
                       name=f"audition_c{c['n']}", note=f"ACE-Step candidate {c['item']} (seed {c['seed']})",
                       console=console)
        if not dry_run:
            m = ffmpeg_measure(ROOT / c["path"])
            out.append({**c, "film": qc["path"], "candidate_lufs": m})
    if out:
        atomic_write_json(OUTPUTS / STAGE / "auditions.json", out)
    return out


def ffmpeg_measure(path: Path) -> dict:
    from .assemble import measure

    m = measure(path)
    return {"I": float(m["input_i"]), "TP": float(m["input_tp"]), "LRA": float(m["input_lra"])}


def run_music(profile: str | None = None, *, push: bool = False, pull: bool = False, audition_only: bool = False,
              force: list[str] | None = None, dry_run: bool = False, console=None, audition: bool = False) -> dict:
    from rich.console import Console

    from .common import storyboard as sbm
    from .common.cache import OUTPUTS
    from .providers import registry
    from .shots import kaggle_round, stale_jobs

    console = console or Console()
    sb = sbm.load_storyboard()
    if audition or audition_only:
        res = audition(sb, dry_run=dry_run, console=console)
        return {"auditions": res}
    tl = sbm.timeline(sb, sbm.load_timing())
    ace = registry.get_provider(STAGE, profile).primary
    manifest = Manifest(STAGE)
    jobs = ace_jobs(sb, tl["total_s"], ace.model, ace.params, ace.name)
    stale = stale_jobs(jobs, manifest, None, force)
    res = kaggle_round(ace, stale, OUTPUTS / STAGE, manifest, stage=STAGE, push=push, pull=pull,
                       extra={"repo": ace.params.get("repo", "https://github.com/ace-step/ACE-Step-1.5.git")},
                       dry_run=dry_run, say=console.print)
    if res.get("ingested"):
        res["auditions"] = audition(sb, dry_run=dry_run, console=console)
    return res
