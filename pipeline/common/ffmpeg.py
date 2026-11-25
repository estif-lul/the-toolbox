"""FFmpeg / ffprobe runner. Commands are built as argument lists (no shell), can be printed in
dry-run mode, and always run with the repo root as cwd so relative paths work in filters
(the `subtitles=` filter in particular, which mis-parses Windows drive letters like `C:`)."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from .env import ROOT


class FFmpegError(RuntimeError):
    def __init__(self, cmd: Sequence[str], returncode: int, stderr: str):
        self.cmd, self.returncode, self.stderr = list(cmd), returncode, stderr
        tail = "\n".join(stderr.strip().splitlines()[-15:])
        super().__init__(f"{Path(cmd[0]).name} exited {returncode}\n  cmd: {fmt_cmd(cmd)}\n{tail}")


def binary(name: str = "ffmpeg") -> str:
    found = shutil.which(name)
    if not found:
        raise FileNotFoundError(f"{name} not found on PATH; install FFmpeg (https://ffmpeg.org/download.html)")
    return found


def fmt_cmd(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(str(c)) for c in cmd)


def run(args: Sequence[str | Path], *, dry_run: bool = False, cwd: Path = ROOT,
        timeout: float | None = 1800) -> subprocess.CompletedProcess | None:
    """Run ffmpeg with `args` (without the leading 'ffmpeg'). Raises FFmpegError with stderr."""
    cmd = [binary("ffmpeg"), "-hide_banner", "-nostdin", "-y", *map(str, args)]
    if dry_run:
        print(fmt_cmd(cmd))
        return None
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)
    if proc.returncode != 0:
        raise FFmpegError(cmd, proc.returncode, proc.stderr)
    return proc


def probe(path: Path | str) -> dict:
    """ffprobe JSON, plus convenience keys: duration (s), video {w,h,fps}, audio {rate,channels}."""
    cmd = [binary("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise FFmpegError(cmd, proc.returncode, proc.stderr)
    info = json.loads(proc.stdout)
    info["duration"] = float(info.get("format", {}).get("duration", 0.0) or 0.0)
    for s in info.get("streams", []):
        if s.get("codec_type") == "video" and "video" not in info:
            num, _, den = (s.get("r_frame_rate") or "0/1").partition("/")
            fps = float(num) / float(den or 1) if float(den or 1) else 0.0
            info["video"] = {"w": s.get("width"), "h": s.get("height"), "fps": round(fps, 3),
                             "codec": s.get("codec_name"), "frames": int(s.get("nb_frames", 0) or 0)}
        if s.get("codec_type") == "audio" and "audio" not in info:
            info["audio"] = {"rate": int(s.get("sample_rate", 0) or 0), "channels": s.get("channels"),
                             "codec": s.get("codec_name")}
    return info
