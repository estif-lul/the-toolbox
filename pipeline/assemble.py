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


# ---------------------------------------------------------------------------------------------
# Step 3: the rough Ken Burns film (the safety net: from here on there is always a film)

SUB_STYLES = {  # PlayRes set to the frame so FontSize and margins are real pixels
    "9x16": ("PlayResX=720,PlayResY=1280,FontName=Arial,FontSize=40,PrimaryColour=&H00FFFFFF,"
             "OutlineColour=&H00000000,BorderStyle=1,Outline=2.5,Shadow=1,Alignment=2,"
             "MarginL=40,MarginR=40,MarginV=280"),
    "16x9": ("PlayResX=1280,PlayResY=720,FontName=Arial,FontSize=40,PrimaryColour=&H00FFFFFF,"
             "OutlineColour=&H00000000,BorderStyle=1,Outline=2.5,Shadow=1,Alignment=2,MarginV=40"),
}


def frame_counts(tl: dict, fps: int = FPS) -> list[int]:
    """Frames per shot (then the end card) by cumulative rounding, so the cut never drifts
    from the timeline the narration and subtitles use."""
    edges = [s["start_s"] for s in tl["shots"]] + [tl["end_card"]["start_s"], tl["total_s"]]
    frames = [round(t * fps) for t in edges]
    return [b - a for a, b in zip(frames, frames[1:])]


def segment_filters(segments: list[dict], export: str) -> tuple[str, int]:
    """Filter chains for each segment -> [s0][s1]... and the number of inputs they use.
    segment = {kind: clip|split|card, inputs: [...], focus: [...], frames: n}."""
    from .common.crops import FULL, HALF, export_crop

    W, H = FULL[export]
    hw, hh = HALF[export]
    parts, idx = [], 0

    def tail(n: int) -> str:
        return (f"fps={FPS},setsar=1,format=yuv420p,tpad=stop_mode=clone:stop_duration=2,"
                f"trim=end_frame={n},setpts=PTS-STARTPTS")

    for k, seg in enumerate(segments):
        n = seg["frames"]
        if seg["kind"] == "clip":
            x, y, w, h = export_crop(export, seg["focus"][0])
            parts.append(f"[{idx}:v]crop={w}:{h}:{x}:{y},scale={W}:{H}:flags=lanczos,{tail(n)}[s{k}]")
            idx += 1
        elif seg["kind"] == "split":
            halves = []
            for j, focus in enumerate(seg["focus"][:2]):
                x, y, w, h = export_crop(export, focus, half=True)
                parts.append(f"[{idx}:v]crop={w}:{h}:{x}:{y},scale={hw}:{hh}:flags=lanczos,fps={FPS},setsar=1,"
                             f"format=yuv420p[s{k}h{j}]")
                halves.append(f"[s{k}h{j}]")
                idx += 1
            stack = "vstack" if export == "9x16" else "hstack"
            parts.append(f"{''.join(halves)}{stack}=inputs=2,{tail(n)}[s{k}]")
        else:  # a still card (placeholder or end card), already W x H
            parts.append(f"[{idx}:v]scale={W}:{H},{tail(n)}[s{k}]")
            idx += 1
    return ";".join(parts), idx


def rough_segments(sb: dict, tl: dict, kb_manifest: dict, export: str) -> list[dict]:
    from .common import endcard
    from .common.crops import FULL
    from .keyframes import keyframe_items

    counts = frame_counts(tl)
    by_shot: dict[str, list[dict]] = {}
    for it in keyframe_items(sb):
        by_shot.setdefault(it["shot"], []).append(it)
    shots = {s["id"]: s for s in sb["shots"]}
    W, H = FULL[export]
    segs = []
    for st, n in zip(tl["shots"], counts):
        items = by_shot[st["shot_id"]]
        clips = [kb_manifest.get(it["id"]) for it in items]
        if all(clips):
            kind = "split" if len(items) == 2 else "clip"
            segs.append({"kind": kind, "inputs": [c["path"] for c in clips],
                         "focus": [it["crop_focus"] for it in items], "frames": n, "shot": st["shot_id"]})
        else:
            card = TMP / f"pending_{st['shot_id']}_{export}.png"
            endcard.card([f"{st['shot_id']} - {shots[st['shot_id']].get('beat', '')}", "picture pending"], W, H, card)
            segs.append({"kind": "card", "inputs": [rel(card)], "focus": [], "frames": n, "shot": st["shot_id"],
                         "pending": True})
    ec = TMP / f"endcard_{export}.png"
    endcard.card(list((sb.get("end_card") or {}).get("lines") or ["Made with AI"]), W, H, ec)
    segs.append({"kind": "card", "inputs": [rel(ec)], "focus": [], "frames": counts[-1], "shot": "end_card"})
    return segs


def rough_args(segments: list[dict], export: str, srt: Path, audio_src: Path, out: Path) -> list[str]:
    args: list[str] = []
    for seg in segments:
        for p in seg["inputs"]:
            if seg["kind"] == "card":
                args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{seg['frames'] / FPS + 2:.3f}"]
            args += ["-i", p]
    chains, n_inputs = segment_filters(segments, export)
    labels = "".join(f"[s{k}]" for k in range(len(segments)))
    graph = (f"{chains};{labels}concat=n={len(segments)}:v=1:a=0[cat];"
             f"[cat]subtitles={rel(srt)}:force_style='{SUB_STYLES[export]}'[v]")
    return args + ["-i", rel(audio_src), "-filter_complex", graph, "-map", "[v]", "-map", f"{n_inputs}:a",
                   "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
                   "-c:a", "copy", "-movflags", "+faststart",
                   "-metadata", "comment=Made with AI - rough Ken Burns cut (draft)", "-shortest", rel(out)]


def run_rough(*, profile: str | None = None, dry_run: bool = False, console=None) -> dict:
    """Ken Burns pictures + the radio cut's mixed sound, both aspect ratios."""
    from rich.console import Console

    from .common.cache import Manifest
    from .shots import run_kenburns

    console = console or Console()
    sb = sbm.load_storyboard()
    timing = sbm.load_timing()
    if timing is None:
        raise AssemblyError("no outputs/narration/timing.json yet: run `make narration` first")
    radio = CUTS / "radio_cut.mp4"
    if not radio.exists():
        raise AssemblyError("no outputs/cuts/radio_cut.mp4 yet: run `make radio` first (the rough cut reuses its mix)")
    tl = sbm.timeline(sb, timing)
    run_kenburns(profile, sb=sb, dry_run=dry_run, console=console)
    kb = Manifest("kenburns").entries
    TMP.mkdir(parents=True, exist_ok=True)
    srt = CUTS / "rough.srt"  # narration only: the end card is a picture here
    atomic_write_text(srt, subtitles.to_srt(subtitles.build_cues(sb, tl, line_pauses(timing))))
    results = {}
    for export in ("9x16", "16x9"):
        segs = rough_segments(sb, tl, kb, export)
        out = CUTS / f"rough_kb_{export}.mp4"
        ffmpeg.run(rough_args(segs, export, srt, radio, out), dry_run=dry_run)
        pending = [s["shot"] for s in segs if s.get("pending")]
        if not dry_run:
            p = ffmpeg.probe(out)
            results[export] = {"path": rel(out), "duration_s": round(p["duration"], 3), "video": p.get("video"),
                               "pending": pending}
            console.print(f"rough cut {export}: {rel(out)} ({p['duration']:.1f}s, {p['video']['w']}x{p['video']['h']})"
                          + (f"; pictures pending: {', '.join(pending)}" if pending else ""))
    if not dry_run:
        atomic_write_json(CUTS / "rough_qc.json", {"timeline_s": tl["total_s"], "exports": results})
    return results
