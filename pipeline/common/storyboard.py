"""Load and validate storyboard.json, and compute the timeline from it.

`validate(sb)` = JSON Schema (Draft 2020-12, schema/storyboard.schema.json, written in Step 1)
+ the semantic checks of PLAN.md §2.2. It returns a `Report` with errors and warnings; any error
stops a run before a single model call is made.

`timeline(sb, timing)` turns measured narration durations (outputs/narration/timing.json, written
in Step 2) into shot starts and durations. Before timing exists, durations are estimated from word
counts at ESTIMATE_WPS so the planner can see roughly where it stands.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .env import ROOT

STORYBOARD = ROOT / "storyboard.json"
SCHEMA = ROOT / "schema" / "storyboard.schema.json"
TIMING = ROOT / "outputs" / "narration" / "timing.json"

SHOT_ID = re.compile(r"^s\d{2}$")
MIN_SHOTS, MAX_SHOTS = 8, 12
WORDS_MIN, WORDS_MAX = 120, 230
ESTIMATE_WPS = 2.3          # words per second, used only until real TTS timing exists
DEFAULT_LINE_GAP_S = 0.35   # silence between two narration lines in the same shot

# Soft privacy lint (PLAN.md §2.2 check 8): phone numbers, plate-like strings, emails.
PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d\s\-]{7,}\d)(?!\d)")
PLATE = re.compile(r"\b(?:AA|OR|AM|TG|SD|ET)?\s?\d-?[A-Z]?\d{4,6}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def load_storyboard(path: Path | str = STORYBOARD) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_timing(path: Path | str = TIMING) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_errors(sb: dict, schema_path: Path) -> list[str]:
    from jsonschema import Draft202012Validator

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    out = []
    for err in sorted(validator.iter_errors(sb), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(root)"
        out.append(f"schema: {where}: {err.message}")
    return out


def _words(text: str) -> int:
    return len(text.split())


def _iter_strings(obj: Any, path: str = ""):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _iter_strings(v, f"{path}/{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _iter_strings(v, f"{path}/{i}")


def narration_lines(shot: dict) -> list[dict]:
    return list(shot.get("narration") or [])


def validate(sb: dict, *, schema_path: Path | None = SCHEMA, timing: dict | None = None) -> Report:
    rep = Report()

    if schema_path is not None and Path(schema_path).exists():
        rep.errors.extend(_schema_errors(sb, Path(schema_path)))
    elif schema_path is not None:
        rep.warn(f"no schema at {Path(schema_path).name}; only semantic checks ran (schema is written in Step 1)")

    shots = sb.get("shots") or []
    char_ids = {c.get("id") for c in sb.get("characters") or []}
    voices = set((sb.get("voices") or {}).keys())

    # 1. ids unique, well formed, 8-12 shots
    ids = [s.get("id") for s in shots]
    if not MIN_SHOTS <= len(shots) <= MAX_SHOTS:
        rep.error(f"need {MIN_SHOTS}-{MAX_SHOTS} shots, found {len(shots)}")
    seen = set()
    for sid in ids:
        if not isinstance(sid, str) or not SHOT_ID.match(sid):
            rep.error(f"shot id {sid!r} must match ^s\\d{{2}}$")
        if sid in seen:
            rep.error(f"duplicate shot id {sid}")
        seen.add(sid)

    line_ref = {(s.get("id"), i) for s in shots for i, _ in enumerate(narration_lines(s))}
    total_words = 0
    prev_move = None
    for shot in shots:
        sid = shot.get("id")
        # 2. character references (shot level and per layer)
        refs = list(shot.get("characters") or [])
        for layer in shot.get("layers") or []:
            refs += list(layer.get("characters") or [])
        for ch in refs:
            if ch not in char_ids:
                rep.error(f"{sid}: unknown character {ch!r} (known: {sorted(char_ids)})")
        # 3. narration voices and echo references
        for i, line in enumerate(narration_lines(shot)):
            if "echo_of" in line:
                target = str(line["echo_of"]).split(":")
                if len(target) != 2 or (target[0], int(target[1]) if target[1].isdigit() else -1) not in line_ref:
                    rep.error(f"{sid}: narration[{i}] echo_of {line['echo_of']!r} does not point at an existing line")
                continue
            if line.get("voice") not in voices:
                rep.error(f"{sid}: narration[{i}] uses unknown voice {line.get('voice')!r}")
            total_words += _words(line.get("text", ""))
        # 4. every shot has a reason
        if not str(shot.get("reason") or "").strip():
            rep.error(f"{sid}: missing 'reason' (every shot needs one)")
        # 9. motion prompts and Ken Burns moves
        if shot.get("motion") == "wan" and not str(shot.get("motion_prompt") or "").strip():
            rep.error(f"{sid}: motion is 'wan' but motion_prompt is empty")
        move = (shot.get("kenburns") or {}).get("move")
        if not move:
            rep.error(f"{sid}: needs a kenburns move (the fallback for every shot)")
        elif move == prev_move:
            rep.warn(f"{sid}: same Ken Burns move as the previous shot ({move})")
        prev_move = move

    # 5. narration length (soft; the hard check needs real timing)
    if total_words and not WORDS_MIN <= total_words <= WORDS_MAX:
        rep.warn(f"narration is {total_words} words; aim for {WORDS_MIN}-{WORDS_MAX}")

    # 6. hard duration check once timing exists
    if timing is not None and shots:
        try:
            tl = timeline(sb, timing)
            fmt = sb.get("format") or {}
            bounds = fmt.get("target_duration_s") or {"min": 60, "max": 90}
            total = tl["total_s"]
            if not bounds["min"] <= total <= bounds["max"]:
                longest = sorted(tl["shots"], key=lambda s: -s["duration_s"])[:3]
                hint = ", ".join(f"{s['shot_id']} ({s['duration_s']:.1f}s)" for s in longest)
                verb = "trim" if total > bounds["max"] else "extend"
                rep.error(f"film is {total:.1f}s incl. end card; must be {bounds['min']}-{bounds['max']}s. "
                          f"{verb.capitalize()} narration, longest shots: {hint}")
        except KeyError as exc:
            rep.error(f"timing.json is missing a line: {exc}")

    # 7. music cues cover every shot
    order = {sid: i for i, sid in enumerate(ids)}
    covered: set[int] = set()
    for cue in ((sb.get("music") or {}).get("cues") or []):
        a, b = cue.get("from_shot"), cue.get("to_shot")
        if a not in order or b not in order:
            rep.error(f"music cue {cue.get('id')!r}: from_shot/to_shot must be existing shots")
            continue
        covered.update(range(order[a], order[b] + 1))
    if shots and (sb.get("music") or {}).get("cues") is not None:
        missing = [ids[i] for i in range(len(ids)) if i not in covered]
        if missing:
            rep.error(f"music cues do not cover shots: {', '.join(map(str, missing))}")

    # 8. soft privacy lint
    for where, text in _iter_strings({k: v for k, v in sb.items() if k != "end_card"}):
        for pattern, what in ((EMAIL, "an email address"), (PHONE, "a phone number"), (PLATE, "a licence plate")):
            if pattern.search(text):
                rep.warn(f"privacy: {where} looks like it contains {what}: {text[:60]!r}")

    return rep


def _line_duration(timing: dict | None, sid: str, idx: int, line: dict, sb_shots: dict) -> float:
    if timing is not None:
        shots = timing.get("shots", timing)
        for entry in shots.get(sid, []):
            if entry.get("line_idx") == idx:
                return float(entry["duration_s"])
        raise KeyError(f"{sid}:{idx}")
    if "echo_of" in line:
        tsid, tidx = str(line["echo_of"]).split(":")
        return _line_duration(None, tsid, int(tidx), narration_lines(sb_shots[tsid])[int(tidx)], sb_shots)
    return max(_words(line.get("text", "")) / ESTIMATE_WPS, 0.6)


def timeline(sb: dict, timing: dict | None = None) -> dict:
    """Shot starts/durations and absolute narration offsets. Estimated if `timing` is None."""
    gap = float((sb.get("format") or {}).get("line_gap_s", DEFAULT_LINE_GAP_S))
    by_id = {s["id"]: s for s in sb.get("shots") or []}
    t = 0.0
    out = []
    for shot in sb.get("shots") or []:
        sid = shot["id"]
        lines = []
        cursor = float(shot.get("pad_before_s", 0.0))
        for i, line in enumerate(narration_lines(shot)):
            d = _line_duration(timing, sid, i, line, by_id)
            lines.append({"line_idx": i, "offset_s": round(t + cursor, 3), "duration_s": round(d, 3)})
            cursor += d + gap
        speech = (cursor - gap) if lines else cursor
        natural = speech + float(shot.get("pad_after_s", 0.0))
        duration = shot.get("duration_override_s") or max(float(shot.get("min_duration_s", 0.0)), natural)
        out.append({"shot_id": sid, "start_s": round(t, 3), "duration_s": round(float(duration), 3),
                    "narration": lines})
        t += float(duration)
    end_card = float((sb.get("end_card") or {}).get("duration_s", 3.0))
    return {"shots": out, "end_card": {"start_s": round(t, 3), "duration_s": end_card},
            "total_s": round(t + end_card, 3), "estimated": timing is None}
