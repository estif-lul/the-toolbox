"""Subtitles from the storyboard + the timeline (shared by the radio cut and the final edit).

- Each narration line becomes one or more cues of at most 2 rows x 40 characters, broken at
  sentence or clause punctuation first and at spaces only when a clause is too long.
- A line's cues share its measured audio span in proportion to their character counts; each
  cue shows for at least 1.0 s and is held up to HOLD_S after the voice stops (never into the
  next cue), so short lines stay readable on a phone.
- A line with a `subtitle` override (Dad's Amharic, shown as its English translation) and an echo
  line are set in italics: they are Dad's voice, not the narrator's.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CHARS = 40
MAX_ROWS = 2
MIN_CUE_S = 1.0
HOLD_S = 0.5
GAP_S = 0.04          # minimum gap between two cues

_CLAUSE = re.compile(r"(?<=[.!?…:;,])\s+")


@dataclass
class Cue:
    start: float
    end: float
    rows: list[str]
    italic: bool = False
    ref: str = ""

    @property
    def text(self) -> str:
        body = "\n".join(self.rows)
        return f"<i>{body}</i>" if self.italic else body


def _wrap_rows(text: str, width: int = MAX_CHARS) -> list[str]:
    """Break one cue's text into rows of <= width, as balanced as possible (2 rows max ideally)."""
    if len(text) <= width:
        return [text]
    words = text.split()
    best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if len(a) <= width and len(b) <= width:
            score = abs(len(a) - len(b)) - (15 if a[-1] in ",.:;!?…" else 0)  # a clause break reads best
            if best is None or score < best[0]:
                best = (score, [a, b])
    if best:
        return best[1]
    rows, cur = [], ""  # a word run that cannot fit in two rows: greedy
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            rows.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return rows + ([cur] if cur else [])


def split_text(text: str, width: int = MAX_CHARS, rows: int = MAX_ROWS) -> list[list[str]]:
    """The cues for one line: a list of cues, each a list of rows."""
    limit = width * rows
    text = " ".join(text.split())
    if len(text) <= limit:
        return [_wrap_rows(text, width)]
    clauses = [c for c in _CLAUSE.split(text) if c]
    pieces: list[str] = []
    for clause in clauses:  # a clause longer than a cue is split at spaces
        while len(clause) > limit:
            cut = clause.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            pieces.append(clause[:cut].strip())
            clause = clause[cut:].strip()
        pieces.append(clause)
    cues, cur = [], ""
    for p in pieces:  # pack clauses into cues
        if cur and len(cur) + 1 + len(p) > limit:
            cues.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        cues.append(cur)
    return [_wrap_rows(c, width) for c in cues]


def line_cues(text: str, start: float, duration: float, *, italic: bool = False, ref: str = "",
              pauses: list[tuple[float, float]] | None = None, snap_s: float = 1.5) -> list[Cue]:
    """Cues for one line. Boundaries fall in proportion to characters; when the line's own pauses
    are known (seconds from the line's start), each boundary moves to the nearest pause within
    `snap_s`, so a cue never runs on through a long dramatic silence ("Patience. Then... silence.")."""
    chunks = split_text(text)
    weights = [max(sum(len(r) for r in rows), 1) for rows in chunks]
    total = float(sum(weights))
    edges, acc = [0.0], 0.0
    for w in weights[:-1]:
        acc += duration * w / total
        edges.append(acc)
    edges.append(duration)
    starts, ends = edges[:-1], edges[1:]
    used: set = set()
    for k in range(1, len(chunks)):
        near = [p for p in (pauses or []) if p not in used and abs((p[0] + p[1]) / 2 - edges[k]) <= snap_s
                and starts[k - 1] < p[0] and p[1] < ends[k]]
        if near:
            p = min(near, key=lambda q: abs((q[0] + q[1]) / 2 - edges[k]))
            used.add(p)
            ends[k - 1], starts[k] = p[0], p[1]
    return [Cue(round(start + a, 3), round(start + b, 3), rows, italic, ref)
            for rows, a, b in zip(chunks, starts, ends)]


def finalize(cues: list[Cue], *, min_s: float = MIN_CUE_S, hold_s: float = HOLD_S, gap_s: float = GAP_S,
             film_end: float | None = None) -> list[Cue]:
    """Enforce the minimum duration and the hold, never overlapping the next cue."""
    cues = sorted(cues, key=lambda c: c.start)
    for i, c in enumerate(cues):
        nxt = cues[i + 1].start - gap_s if i + 1 < len(cues) else (film_end if film_end is not None else c.end + hold_s)
        want = max(c.end + hold_s, c.start + min_s)
        c.end = round(max(min(want, nxt), c.end if c.end <= nxt else nxt), 3)
    return cues


def build_cues(sb: dict, tl: dict, pauses: dict[str, list[tuple[float, float]]] | None = None) -> list[Cue]:
    """All cues for the film, from the storyboard text and the timeline's narration offsets.
    `pauses` maps a line ref ("s07:0") to the pauses inside its audio (see line_cues)."""
    by_id = {s["id"]: s for s in sb["shots"]}
    cues: list[Cue] = []
    for shot_t in tl["shots"]:
        shot = by_id[shot_t["shot_id"]]
        lines = shot.get("narration") or []
        for nt in shot_t["narration"]:
            line = lines[nt["line_idx"]]
            ref = f"{shot['id']}:{nt['line_idx']}"
            if "echo_of" in line:
                sid, idx = line["echo_of"].split(":")
                src = by_id[sid]["narration"][int(idx)]
                text = line.get("subtitle") or src.get("subtitle") or src["text"]
                italic = True
            else:
                text = line.get("subtitle") or line["text"]
                italic = bool(line.get("subtitle")) or line.get("lang", "en") != "en"
            cues += line_cues(text, nt["offset_s"], nt["duration_s"], italic=italic, ref=ref,
                              pauses=(pauses or {}).get(ref))
    return finalize(cues, film_end=tl["end_card"]["start_s"])


def _ts(seconds: float) -> str:
    ms = int(round(max(seconds, 0.0) * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(cues: list[Cue]) -> str:
    blocks = [f"{i}\n{_ts(c.start)} --> {_ts(c.end)}\n{c.text}\n" for i, c in enumerate(cues, 1)]
    return "\n".join(blocks)
