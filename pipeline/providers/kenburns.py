"""Ken Burns "provider": a slow, eased pan/zoom over a still, rendered locally with FFmpeg zoompan.

It looks like any other video provider to the pipeline (provider "kenburns", logged with latency
and zero cost), so it can sit at the end of the video fallback chain and always succeed.
The still is upscaled to 4x first: zoompan rounds its crop window to whole pixels, and doing that
on a large image removes the visible jitter of slow moves.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..common import ffmpeg
from .base import BaseAdapter, VideoResult

MOVES = ("push_in", "pull_out", "pan_left", "pan_right", "tilt_up", "tilt_down", "static")


def zoompan_filter(move: str, amount: float, frames: int, size: int, fps: int, upscale: int = 4) -> str:
    """Build the filter string. `e` is a cosine ease from 0 to 1 over the clip."""
    if move not in MOVES:
        raise ValueError(f"unknown Ken Burns move {move!r}; expected one of {MOVES}")
    n = max(frames - 1, 1)
    e = f"(1-cos(PI*on/{n}))/2"
    a = float(amount)
    z = {
        "push_in": f"1+{a}*{e}",
        "pull_out": f"1+{a}*(1-{e})",
        "static": "1",
    }.get(move, f"{1 + a}")  # pans and tilts hold a fixed zoom to have room to move
    cx, cy = "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    x, y = cx, cy
    if move == "pan_left":
        x = f"(iw-iw/zoom)*(1-{e})"
    elif move == "pan_right":
        x = f"(iw-iw/zoom)*{e}"
    elif move == "tilt_up":
        y = f"(ih-ih/zoom)*(1-{e})"
    elif move == "tilt_down":
        y = f"(ih-ih/zoom)*{e}"
    big = size * upscale
    return (f"scale={big}:{big}:flags=lanczos,"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={size}x{size}:fps={fps},"
            f"setsar=1,format=yuv420p")


class KenBurns(BaseAdapter):
    name = "kenburns"

    def render(self, image: Path, out: Path, *, duration_s: float, move: str = "push_in",
               amount: float = 0.08, fps: int | None = None, size: int | None = None,
               dry_run: bool = False) -> VideoResult:
        fps = int(fps or self.params.get("fps", 24))
        size = int(size or self.params.get("size", 1024))
        frames = max(int(round(duration_s * fps)), 1)
        vf = zoompan_filter(move, amount, frames, size, fps, int(self.params.get("upscale", 4)))
        out.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        ffmpeg.run(["-i", image, "-vf", vf, "-frames:v", str(frames), "-r", str(fps),
                    "-c:v", "libx264", "-crf", str(self.params.get("crf", 18)), "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], dry_run=dry_run)
        meta: dict[str, Any] = {"move": move, "amount": amount, "frames": frames, "fps": fps, "size": size}
        return VideoResult(job_id=out.stem, ok=True, path=out, seconds=time.perf_counter() - t0, meta=meta)
