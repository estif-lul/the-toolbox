"""Small, dependency-free WAV tools for the narration stage (16-bit PCM, any rate).

- `envelope_db`: RMS level per 10 ms window, in dBFS.
- `find_silences` / `speech_bounds`: where the speech is, from the envelope.
- `trim`: cut leading and trailing silence, keeping a short margin so word onsets and soft
  endings are never clipped (conservative on purpose).
- `split_points`: where to cut one TTS response that holds several lines (the free tier allows
  only a few TTS requests a day, so lines are batched; see pipeline/narration.py). The lines are
  separated by long pauses; the cuts are the pauses that best match the expected length of each
  line (dynamic programming over the candidate pauses), and the result says how sure it is.

Pure Python on purpose: TTS clips are short (a minute of 24 kHz mono is 1.4 M samples), and the
logic is unit-tested on synthetic signals without FFmpeg.
"""

from __future__ import annotations

import array
import io
import math
import sys
import wave
from dataclasses import dataclass, field
from pathlib import Path

WIN_S = 0.01               # analysis window
SILENCE_DB = -50.0         # TTS silence measured at -70..-90 dBFS, speech at -10..-30 dBFS
MIN_PAUSE_S = 0.2          # shorter dips are gaps between words, not pauses
KEEP_BEFORE_S = 0.05       # margin kept before the first word
KEEP_AFTER_S = 0.12        # margin kept after the last word (soft endings, breaths)


@dataclass
class Clip:
    samples: array.array   # signed 16-bit, mono
    rate: int

    @property
    def duration_s(self) -> float:
        return len(self.samples) / float(self.rate)

    def slice(self, start_s: float, end_s: float) -> "Clip":
        a = max(0, int(round(start_s * self.rate)))
        b = min(len(self.samples), int(round(end_s * self.rate)))
        return Clip(self.samples[a:b], self.rate)


def read_wav(src: Path | str | bytes) -> Clip:
    fh = wave.open(io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else str(src), "rb")
    with fh as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"expected 16-bit PCM, got {8 * w.getsampwidth()}-bit")
        channels, rate = w.getnchannels(), w.getframerate()
        data = array.array("h", w.readframes(w.getnframes()))
    if sys.byteorder == "big":  # WAV is little-endian
        data.byteswap()
    if channels > 1:  # downmix (TTS is mono; this only guards against surprises)
        data = array.array("h", (int(sum(data[i:i + channels]) / channels) for i in range(0, len(data), channels)))
    return Clip(data, rate)


def wav_bytes(clip: Clip) -> bytes:
    data = clip.samples
    if sys.byteorder == "big":
        data = array.array("h", data)
        data.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(clip.rate)
        w.writeframes(data.tobytes())
    return buf.getvalue()


def silence(seconds: float, rate: int) -> Clip:
    return Clip(array.array("h", bytes(2 * max(0, int(round(seconds * rate))))), rate)


def concat(clips: list[Clip], gap_s: float = 0.0) -> Clip:
    if not clips:
        raise ValueError("nothing to concatenate")
    rate = clips[0].rate
    out = array.array("h")
    for i, c in enumerate(clips):
        if c.rate != rate:
            raise ValueError("clips must share a sample rate")
        if i and gap_s > 0:
            out.extend(silence(gap_s, rate).samples)
        out.extend(c.samples)
    return Clip(out, rate)


def envelope_db(clip: Clip, win_s: float = WIN_S) -> list[float]:
    win = max(1, int(round(clip.rate * win_s)))
    s = clip.samples
    out = []
    for i in range(0, len(s), win):
        chunk = s[i:i + win]
        if not chunk:
            break
        rms = math.sqrt(sum(x * x for x in chunk) / len(chunk))
        out.append(20 * math.log10(max(rms, 1.0) / 32768.0))
    return out


def loud_mask(env: list[float], threshold_db: float = SILENCE_DB, *, min_run: int = 4,
              isolation: int = 10) -> list[bool]:
    """Which windows hold sound. A blip shorter than `min_run` windows (40 ms) with at least
    `isolation` windows (100 ms) of silence on both sides is noise, not speech: a -49.7 dBFS click
    in the middle of a 3 s pause was seen in a real take (it kept 1.2 s of dead air after a line)."""
    loud = [level >= threshold_db for level in env]
    runs, start = [], None
    for i, flag in enumerate(loud + [False]):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            runs.append((start, i))
            start = None
    for k, (a, b) in enumerate(runs):
        if b - a >= min_run:
            continue
        gap_before = a - runs[k - 1][1] if k else a
        gap_after = runs[k + 1][0] - b if k + 1 < len(runs) else len(env) - b
        if gap_before >= isolation and gap_after >= isolation:
            for i in range(a, b):
                loud[i] = False
    return loud


def find_silences(env: list[float], win_s: float = WIN_S, threshold_db: float = SILENCE_DB,
                  min_len_s: float = MIN_PAUSE_S) -> list[tuple[float, float]]:
    """Runs of windows below the threshold that last at least `min_len_s`, as (start_s, end_s)."""
    mask = loud_mask(env, threshold_db)
    out, start = [], None
    for i, is_loud in enumerate(mask + [True]):  # sentinel closes a trailing run
        if not is_loud:
            if start is None:
                start = i
        elif start is not None:
            if (i - start) * win_s >= min_len_s:
                out.append((round(start * win_s, 3), round(min(i, len(env)) * win_s, 3)))
            start = None
    return out


def speech_bounds(env: list[float], win_s: float = WIN_S,
                  threshold_db: float = SILENCE_DB) -> tuple[float, float] | None:
    loud = [i for i, is_loud in enumerate(loud_mask(env, threshold_db)) if is_loud]
    if not loud:
        return None
    return round(loud[0] * win_s, 3), round((loud[-1] + 1) * win_s, 3)


def trim(clip: Clip, *, threshold_db: float = SILENCE_DB, keep_before_s: float = KEEP_BEFORE_S,
         keep_after_s: float = KEEP_AFTER_S) -> tuple[Clip, float, float]:
    """(trimmed clip, start_s, end_s in the source). A silent clip is returned unchanged."""
    bounds = speech_bounds(envelope_db(clip), threshold_db=threshold_db)
    if bounds is None:
        return clip, 0.0, clip.duration_s
    start = max(0.0, bounds[0] - keep_before_s)
    end = min(clip.duration_s, bounds[1] + keep_after_s)
    return clip.slice(start, end), round(start, 3), round(end, 3)


@dataclass
class SplitResult:
    cuts: list[float]                       # cut times (s), len = n_lines - 1
    segments: list[tuple[float, float]]     # speech span per line (s)
    ratios: list[float]                     # measured / expected length per line
    boundary_pauses: list[float]            # length of the pause chosen at each cut (s)
    longest_unused_pause: float             # the longest interior pause that is not a cut (s)
    ok: bool
    problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"cuts": self.cuts, "segments": self.segments, "ratios": [round(r, 3) for r in self.ratios],
                "boundary_pauses": self.boundary_pauses, "longest_unused_pause": self.longest_unused_pause,
                "ok": self.ok, "problems": self.problems}


def split_points(silences: list[tuple[float, float]], bounds: tuple[float, float], weights: list[float],
                 *, pause_weight: float = 1.0, min_ratio: float = 0.4, max_ratio: float = 2.5,
                 min_boundary_s: float = 0.3) -> SplitResult:
    """Choose len(weights)-1 of the interior pauses as the cuts between lines.

    `weights` is the expected relative length of each line (e.g. its letter count). The cost of a
    choice is sum(ln(measured/expected)^2) over the lines + pause_weight * sum(ln(longest/len))
    over the chosen pauses, so long pauses whose spacing matches the text win.
    """
    n = len(weights)
    start, end = bounds
    if n == 1:
        return SplitResult([], [(start, end)], [1.0], [], 0.0, True)
    cands = [(a, b) for a, b in silences if a > start and b < end]
    if len(cands) < n - 1:
        return SplitResult([], [], [], [], 0.0, False,
                           [f"found {len(cands)} pause(s) for {n} lines; the response may have skipped a line"])
    longest = max(b - a for a, b in cands)
    # Speech time left once the n-1 longest pauses (the likely cuts) are taken out.
    likely = sum(sorted((b - a for a, b in cands), reverse=True)[:n - 1])
    speech = max(end - start - likely, 1e-3)
    total_w = float(sum(weights)) or 1.0
    expected = [speech * w / total_w for w in weights]

    def seg_cost(i: int, seg_start: float, seg_end: float) -> float:
        d = max(seg_end - seg_start, 1e-3)
        return math.log(d / expected[i]) ** 2

    def pause_cost(j: int) -> float:
        a, b = cands[j]
        return pause_weight * math.log(longest / max(b - a, 1e-3))

    INF = float("inf")
    k = len(cands)
    # best[i][j]: cost of lines 0..i with the cut after line i at pause j
    best = [[INF] * k for _ in range(n - 1)]
    back = [[-1] * k for _ in range(n - 1)]
    for j in range(k):
        best[0][j] = seg_cost(0, start, cands[j][0]) + pause_cost(j)
    for i in range(1, n - 1):
        for j in range(i, k):
            for p in range(i - 1, j):
                if best[i - 1][p] == INF:
                    continue
                c = best[i - 1][p] + seg_cost(i, cands[p][1], cands[j][0]) + pause_cost(j)
                if c < best[i][j]:
                    best[i][j], back[i][j] = c, p
    final, last = INF, -1
    for j in range(n - 2, k):
        if best[n - 2][j] == INF:
            continue
        c = best[n - 2][j] + seg_cost(n - 1, cands[j][1], end)
        if c < final:
            final, last = c, j
    chosen = [last]
    for i in range(n - 2, 0, -1):
        chosen.append(back[i][chosen[-1]])
    chosen.reverse()

    segments, edge = [], start
    for j in chosen:
        segments.append((round(edge, 3), cands[j][0]))
        edge = cands[j][1]
    segments.append((round(edge, 3), round(end, 3)))
    ratios = [max(b - a, 1e-3) / expected[i] for i, (a, b) in enumerate(segments)]
    pauses = [round(cands[j][1] - cands[j][0], 3) for j in chosen]
    unused = [b - a for j, (a, b) in enumerate(cands) if j not in chosen]
    longest_unused = round(max(unused), 3) if unused else 0.0
    problems = []
    for i, r in enumerate(ratios):
        if not min_ratio <= r <= max_ratio:
            problems.append(f"line {i}: {r:.2f}x its expected length")
    if min(pauses) < min_boundary_s:
        problems.append(f"a cut sits on a {min(pauses):.2f}s pause (< {min_boundary_s}s)")
    if longest_unused > min(pauses):
        problems.append(f"an unused pause ({longest_unused:.2f}s) is longer than a chosen one ({min(pauses):.2f}s)")
    cuts = [round((cands[j][0] + cands[j][1]) / 2, 3) for j in chosen]
    # The last problem alone is a warning (a long dramatic pause inside a line); the others fail.
    hard = [p for p in problems if not p.startswith("an unused pause")]
    return SplitResult(cuts, segments, ratios, pauses, longest_unused, not hard, problems)


def text_weight(text: str) -> float:
    """Expected relative spoken length: letters (Ge'ez letters are syllables, but a batch holds
    one voice and one language, so only the proportions matter) plus a little for punctuation pauses."""
    letters = sum(ch.isalpha() for ch in text)
    pauses = sum(text.count(p) for p in (",", ".", ":", ";", "…", "?", "!", "።", "፣"))
    return letters + 4.0 * pauses
