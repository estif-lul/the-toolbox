"""Assembly. Step 2 builds the **radio cut** (`make radio`): the whole film as sound and subtitles
on black, so people can react to the story before a single picture exists.

    timeline (storyboard + timing.json)
      -> narration stem: every line at its offset (adelay), the s09 echo quieter with a soft
         reverb (aecho, no new TTS call), mixed with amix normalize=0 -> outputs/cuts/narration_stem.wav
      -> placeholder pad (pipeline/music.py), pre-set to a quiet level, ducked under the voice
         with sidechaincompress (threshold/ratio/attack/release from storyboard.music.duck)
      -> narration + ducked pad -> two-pass loudnorm to I=-14 LUFS, TP=-1 dBTP, LRA=11
      -> black 1280x720 24 fps + burned-in subtitles (common/subtitles.py; also radio_cut.srt)
      -> outputs/cuts/radio_cut.mp4 (H.264/AAC, faststart) + radio_qc.json

Sources are brought to known levels first (narration -16 LUFS, pad -28 LUFS) so the balance is a
choice, not an accident. Everything is FFmpeg: no model calls, so re-running is free.
The final edit (both aspect ratios, pictures, end card) is added here in Step 5.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .common import ffmpeg
from .common import storyboard as sbm
from .common import subtitles
from .common.cache import OUTPUTS, atomic_write_json, atomic_write_text, rel
from .common.env import ROOT

CUTS = OUTPUTS / "cuts"
TMP = CUTS / "tmp"
TARGET = {"I": -14.0, "TP": -1.0, "LRA": 11.0}
NARRATION_LUFS = -16.0
PAD_LUFS = -28.0
RADIO_W, RADIO_H, FPS = 1280, 720, 24
ECHO_FILTER = "apad=pad_dur=0.6,aecho=0.8:0.55:70|140|230:0.35|0.22|0.12,lowpass=f=4500"
# Alignment 2 (bottom centre) means the same in SSA and ASS numbering; 5 is top-left in the legacy
# numbering libass applies to converted SRT. MarginV lifts the text towards the middle of the frame.
SUB_STYLE = ("FontName=Arial,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
             "BorderStyle=1,Outline=1.2,Shadow=0.6,Alignment=2,MarginV=100")


class AssemblyError(RuntimeError):
    pass


@dataclass
class Placement:
    path: str          # repo-relative
    offset_s: float
    gain_db: float = 0.0
    reverb: bool = False
    ref: str = ""


def placements(sb: dict, tl: dict, timing: dict) -> list[Placement]:
    shots = timing.get("shots", timing)
    out = []
    for st in tl["shots"]:
        entries = {e["line_idx"]: e for e in shots[st["shot_id"]]}
        for nt in st["narration"]:
            e = entries[nt["line_idx"]]
            echo = "echo_of" in e
            out.append(Placement(e["path"], nt["offset_s"], float(e.get("gain_db", 0.0)) if echo else 0.0,
                                 bool(e.get("reverb")) if echo else False, f"{st['shot_id']}:{nt['line_idx']}"))
    return out


def stem_filter(items: list[Placement], total_s: float) -> str:
    parts = []
    for i, p in enumerate(items):
        chain = [f"[{i}:a]aformat=sample_fmts=fltp:channel_layouts=mono"]
        if p.gain_db:
            chain.append(f"volume={p.gain_db}dB")
        if p.reverb:
            chain.append(ECHO_FILTER)
        chain.append(f"adelay={int(round(p.offset_s * 1000))}:all=1")
        parts.append(",".join(chain) + f"[n{i}]")
    labels = "".join(f"[n{i}]" for i in range(len(items)))
    parts.append(f"{labels}amix=inputs={len(items)}:normalize=0:dropout_transition=0,"
                 f"apad=whole_dur={total_s:.3f},atrim=0:{total_s:.3f}[stem]")
    return ";".join(parts)


def stem_args(items: list[Placement], total_s: float, out: Path) -> list[str]:
    args: list[str] = []
    for p in items:
        args += ["-i", p.path]
    return args + ["-filter_complex", stem_filter(items, total_s), "-map", "[stem]",
                   "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", rel(out)]


def mix_filter(duck: dict, gain_voice_db: float, gain_pad_db: float, total_s: float) -> str:
    """[0] narration stem, [1] pad -> [mix] (before the final loudness normalisation)."""
    return (f"[0:a]aresample=48000,aformat=channel_layouts=stereo,volume={gain_voice_db:.2f}dB,asplit=2[v][sc];"
            f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={gain_pad_db:.2f}dB,"
            f"apad=whole_dur={total_s:.3f},atrim=0:{total_s:.3f}[pad];"
            f"[pad][sc]sidechaincompress=threshold={duck['threshold']}:ratio={duck['ratio']}:"
            f"attack={duck['attack_ms']}:release={duck['release_ms']}[ducked];"
            f"[ducked][v]amix=inputs=2:normalize=0:duration=first[mix]")


def loudnorm_filter(measured: dict | None = None) -> str:
    base = f"loudnorm=I={TARGET['I']}:TP={TARGET['TP']}:LRA={TARGET['LRA']}"
    if measured is None:
        return base + ":print_format=json"
    return (base + f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}:linear=true:print_format=json")


def parse_loudnorm(stderr: str) -> dict:
    blocks = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr)
    if not blocks:
        raise AssemblyError("loudnorm printed no measurement")
    return json.loads(blocks[-1])


def measure(path: Path | str, *, dry_run: bool = False) -> dict:
    """Integrated loudness etc. of a file (loudnorm's first pass)."""
    proc = ffmpeg.run(["-i", rel(path), "-vn", "-af", loudnorm_filter(), "-f", "null", "-"], dry_run=dry_run)
    if proc is None:
        return {"input_i": "-23.0", "input_tp": "-6.0", "input_lra": "5.0", "input_thresh": "-33.0",
                "target_offset": "0.0"}
    return parse_loudnorm(proc.stderr)


def line_pauses(timing: dict) -> dict[str, list[tuple[float, float]]]:
    """The pauses inside each line's audio (seconds from its start), for subtitle timing."""
    from .common import audio

    out = {}
    for sid, entries in timing.get("shots", timing).items():
        for e in entries:
            env = audio.envelope_db(audio.read_wav(ROOT / e["path"]))
            out[f"{sid}:{e['line_idx']}"] = audio.find_silences(env, min_len_s=0.25)
    return out


def endcard_cue(sb: dict, tl: dict) -> subtitles.Cue:
    lines = (sb.get("end_card") or {}).get("lines") or ["Made with AI"]
    rows = [r for r in lines[:2] if len(r) <= subtitles.MAX_CHARS] or ["Made with AI"]
    ec = tl["end_card"]
    return subtitles.Cue(ec["start_s"], round(ec["start_s"] + ec["duration_s"], 3), rows, False, "end_card")


def run_radio(*, dry_run: bool = False, sb: dict | None = None, timing: dict | None = None,
              console=None) -> dict:
    from rich.console import Console

    from . import music

    console = console or Console()
    sb = sb if sb is not None else sbm.load_storyboard()
    timing = timing if timing is not None else sbm.load_timing()
    if timing is None:
        raise AssemblyError("no outputs/narration/timing.json yet: run `make narration` first")
    report = sbm.validate(sb, timing=timing)
    if not report.ok:
        raise AssemblyError("storyboard does not validate with the measured timing:\n  " + "\n  ".join(report.errors))
    tl = sbm.timeline(sb, timing)
    total = tl["total_s"]
    CUTS.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)

    # subtitles: narration cues + the AI label over the end card's 3 s
    cues = subtitles.build_cues(sb, tl, line_pauses(timing))
    srt_path = CUTS / "radio_cut.srt"
    atomic_write_text(srt_path, subtitles.to_srt(cues + [endcard_cue(sb, tl)]))

    items = placements(sb, tl, timing)
    stem = CUTS / "narration_stem.wav"
    ffmpeg.run(stem_args(items, total, stem), dry_run=dry_run)
    pad = music.placeholder(total, dry_run=dry_run)

    m_voice, m_pad = measure(stem, dry_run=dry_run), measure(pad, dry_run=dry_run)
    g_voice = NARRATION_LUFS - float(m_voice["input_i"])
    g_pad = PAD_LUFS - float(m_pad["input_i"])
    duck = (sb.get("music") or {}).get("duck") or {"threshold": 0.02, "ratio": 6, "attack_ms": 300, "release_ms": 1500}
    premix = TMP / "radio_premix.wav"
    ffmpeg.run(["-i", rel(stem), "-i", rel(pad), "-filter_complex", mix_filter(duck, g_voice, g_pad, total),
                "-map", "[mix]", "-c:a", "pcm_f32le", rel(premix)], dry_run=dry_run)
    m_mix = measure(premix, dry_run=dry_run)

    out = CUTS / "radio_cut.mp4"
    vf = f"[0:v]subtitles={rel(srt_path)}:force_style='{SUB_STYLE}'[v]"
    af = f"[1:a]{loudnorm_filter(m_mix)},aresample=48000[a]"
    ffmpeg.run(["-f", "lavfi", "-i", f"color=c=black:s={RADIO_W}x{RADIO_H}:r={FPS}:d={total:.3f}",
                "-i", rel(premix), "-filter_complex", f"{vf};{af}", "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "28", "-tune", "stillimage",
                "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart", "-metadata", "comment=Made with AI - radio cut (draft, placeholder music)",
                "-shortest", rel(out)], dry_run=dry_run)
    if dry_run:
        return {"status": "dry_run", "total_s": total}

    final = measure(out)
    probed = ffmpeg.probe(out)
    qc = {
        "path": rel(out), "duration_s": round(probed["duration"], 3), "timeline_s": total,
        "video": probed.get("video"), "audio": probed.get("audio"),
        "loudness": {"I": float(final["input_i"]), "TP": float(final["input_tp"]), "LRA": float(final["input_lra"])},
        "sources": {"narration_I": float(m_voice["input_i"]), "pad_I": float(m_pad["input_i"]),
                    "gain_voice_db": round(g_voice, 2), "gain_pad_db": round(g_pad, 2)},
        "cues": len(cues), "lines": len(items), "srt": rel(srt_path), "stem": rel(stem), "music": rel(pad),
        "music_note": "placeholder pad (code-generated), not the film's music",
    }
    qc["ok"] = (abs(qc["loudness"]["I"] - TARGET["I"]) <= 1.0 and qc["loudness"]["TP"] <= TARGET["TP"] + 0.2
                and sbm.validate(sb, timing=timing).ok)
    atomic_write_json(CUTS / "radio_qc.json", qc)
    premix.unlink(missing_ok=True)
    console.print(f"radio cut: {qc['path']} ({qc['duration_s']:.1f}s, {qc['loudness']['I']:.1f} LUFS, "
                  f"TP {qc['loudness']['TP']:.1f} dBTP, {len(cues)} subtitle cues for {len(items)} lines)")
    console.print(f"  subtitles {qc['srt']}; stem {qc['stem']}; music = placeholder pad {qc['music']}")
    return qc
