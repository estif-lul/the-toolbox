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
from .common.cache import Manifest, artifact_path, cache_key
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
