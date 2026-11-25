"""The narration stage (`make narration`) and the voice audition (`make audition`).

Every narration line in storyboard.json becomes one WAV, cached by what decides its sound:

    key = cache_key(stage="narration", provider, model, params={voice, style}, inputs={text})

where `text` is `tts_text` when set (a phonetic re-spelling), and `style` is the line's own style
or else its voice's style. Editing one line's text changes only that line's key, so the next run
makes one TTS request for that line and none for the rest.

**Batching (the free tier allows 10 TTS requests a day per model).** Lines that miss the cache are
grouped by voice, in story order, up to `batch_lines` per request. A batch is one request with one
turn per line (each with its own style) and a `<long pause>` between turns; the response is cut
at the pauses (`common.audio.split_points`, which checks each piece against the length its text
predicts and refuses a doubtful split). A batch of one is a plain single-line request.

Files:
- outputs/narration/batches/<key16>.wav + .json   the response as received + how it was cut
- outputs/narration/<shot>/<key16>.raw.wav          the line's piece of the response
- outputs/narration/<shot>/<key16>.wav              the same, leading/trailing silence trimmed
- outputs/narration/takes.json                      every take ever made, by cache key
- outputs/narration/manifest.json                   the take each line uses now
- outputs/narration/timing.json                     measured durations: drives the timeline

A take made by a fallback model (when the primary's daily quota is gone) is used, and kept until
the line is forced (`--force s05`), so one consistent voice can be restored when quota allows.

**Audition** (EXPERIMENTS.md E02-E04, E18): the same lines in each candidate stock voice, one
request per voice, written into the same take store. Auditioning a role on the primary model
with the storyboard's own lines and styles therefore pre-pays the final narration: choosing that
voice makes the narration stage a cache hit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .common import audio
from .common import storyboard as sbm
from .common.cache import (OUTPUTS, Manifest, artifact_path, atomic_write_bytes, atomic_write_json,
                           cache_key, canonical_json, rel, sha256_bytes, sha256_text)
from .common.env import ROOT
from .common.invoke import invoke
from .common.log import get_run, log_event, now_iso, read_log
from .common.retry import FatalError
from .providers import registry

STAGE = "narration"
STAGE_VERSION = 1
OUT = OUTPUTS / STAGE
TAKES = OUT / "takes.json"
BATCHES = OUT / "batches"
AUDITIONS = OUT / "audition"
DEFAULT_BATCH_LINES = 8
# The narrator audition uses the first and the last line of the film, as planned for E02.
AUDITION_LINES = {"narrator": ["s01:0", "s10:1"]}
LINE_GAP_S = 0.6        # silence between lines in an audition file
VOICE_GAP_S = 1.5       # silence between voices in the audition sheet


class StoryboardInvalid(RuntimeError):
    pass


class SplitFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class Line:
    ref: str            # "s05:1" = shot s05, narration[1]
    shot_id: str
    idx: int
    role: str           # key in storyboard.voices ("narrator", "dad")
    voice: str          # the stock voice name sent to TTS
    style: str | None
    text: str           # what is sent to TTS (tts_text if set)
    lang: str
    words: int          # words of the storyboard text (what the subtitles show)


def plan_lines(sb: dict, *, roles: Iterable[str] | None = None, refs: Iterable[str] | None = None,
               voice_override: str | None = None, no_style: bool = False) -> list[Line]:
    """Every spoken (non-echo) line, in story order. `refs` may hold line refs or shot ids."""
    voices = sb.get("voices") or {}
    roles = set(roles) if roles else None
    refs = set(refs) if refs else None
    out = []
    for shot in sb.get("shots") or []:
        sid = shot["id"]
        for i, line in enumerate(shot.get("narration") or []):
            if "echo_of" in line:
                continue
            ref = f"{sid}:{i}"
            if roles and line["voice"] not in roles:
                continue
            if refs and ref not in refs and sid not in refs:
                continue
            cfg = voices[line["voice"]]
            style = None if no_style else (line.get("style") or cfg.get("style"))
            out.append(Line(ref, sid, i, line["voice"], voice_override or cfg["voice"], style,
                            line.get("tts_text") or line["text"], line.get("lang", "en"),
                            len(line["text"].split())))
    return out


def line_key(line: Line, provider: Any) -> str:
    return cache_key(stage=STAGE, stage_version=STAGE_VERSION, provider=provider.name, model=provider.model,
                     params={"voice": line.voice, "style": line.style}, inputs={"text": line.text})


def batch_key(batch: list[Line], provider: Any) -> str:
    return cache_key(stage=STAGE, stage_version=STAGE_VERSION, provider=provider.name, model=provider.model,
                     params={"voice": batch[0].voice, "batch": len(batch)},
                     inputs=[{"text": ln.text, "style": ln.style} for ln in batch])


def make_batches(lines: list[Line], batch_lines: int) -> list[list[Line]]:
    """Group by stock voice (story order inside a voice), at most `batch_lines` per request."""
    by_voice: dict[str, list[Line]] = {}
    for ln in lines:
        by_voice.setdefault(ln.voice, []).append(ln)
    size = max(1, int(batch_lines))
    batches = [group[i:i + size] for group in by_voice.values() for i in range(0, len(group), size)]
    return sorted(batches, key=lambda b: lines.index(b[0]))


class Takes:
    """outputs/narration/takes.json: cache key -> one generated line (audition or final)."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path or TAKES)
        self.entries: dict[str, dict] = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def get(self, key: str) -> dict | None:
        entry = self.entries.get(key)
        if entry and (ROOT / entry["raw_path"]).exists():
            return entry
        return None

    def put(self, key: str, entry: dict) -> None:
        self.entries[key] = entry
        atomic_write_json(self.path, self.entries)


def trimmed(entry: dict) -> tuple[Path, float]:
    """Make (or refresh) the trimmed file next to the raw take; return its path and duration.
    Trimming is cheap and deterministic, so it is redone on every run rather than cached."""
    raw = ROOT / entry["raw_path"]
    clip, _, _ = audio.trim(audio.read_wav(raw))
    out = raw.with_name(raw.name.replace(".raw.wav", ".wav"))
    data = audio.wav_bytes(clip)
    if not out.exists() or out.read_bytes() != data:
        atomic_write_bytes(out, data)
    return out, round(clip.duration_s, 3)


def synthesize(batch: list[Line], providers: list[Any], takes: Takes) -> dict[str, str]:
    """One TTS request for `batch`; returns {line ref: take key}. Raises SplitFailed if the
    response cannot be cut into the batch's lines with confidence (the response is kept)."""
    voice = batch[0].voice
    items = [(ln.text, ln.style) for ln in batch]

    def call(p):
        if len(batch) == 1:
            return p.synthesize(items[0][0], voice, items[0][1])
        if not hasattr(p, "synthesize_batch"):
            raise FatalError(f"{p.name} cannot batch lines; run with --batch-lines 1")
        return p.synthesize_batch(items, voice)

    def save(p, key, result) -> Path:
        path = OUT / "batches" / f"{key[:16]}.wav"
        atomic_write_bytes(path, result.wav_bytes)
        return path

    r = invoke(providers, call, stage=STAGE, shot_id=",".join(ln.ref for ln in batch),
               params={"voice": voice, "lines": len(batch)}, input_hash=sha256_text(canonical_json(items)),
               key_fn=lambda p: batch_key(batch, p), save=save, max_attempts=2)
    clip = audio.read_wav(r.value.wav_bytes)
    env = audio.envelope_db(clip)
    bounds = audio.speech_bounds(env) or (0.0, clip.duration_s)
    silences = audio.find_silences(env)
    split = audio.split_points(silences, bounds, [audio.text_weight(ln.text) for ln in batch])
    report = {
        "batch_key": r.cache_key, "provider": r.provider.name, "model": r.provider.model, "voice": voice,
        "run_id": get_run().run_id, "created_at": now_iso(), "duration_s": round(clip.duration_s, 3),
        "speech_bounds": bounds, "silences": silences, "split": split.as_dict(),
        "lines": [{"ref": ln.ref, "text": ln.text, "style": ln.style} for ln in batch],
    }
    atomic_write_json(r.output.with_suffix(".json"), report)
    if not split.ok:
        raise SplitFailed(f"cannot cut {rel(r.output)} into {len(batch)} lines: {'; '.join(split.problems)}. "
                          f"Listen to it; re-run with --batch-lines 1 for these lines if needed.")
    edges = [0.0, *split.cuts, clip.duration_s]
    out = {}
    for i, ln in enumerate(batch):
        key = line_key(ln, r.provider)
        raw_path = artifact_path(STAGE, ln.shot_id, key, "raw.wav")
        atomic_write_bytes(raw_path, audio.wav_bytes(clip.slice(edges[i], edges[i + 1])))
        takes.put(key, {
            "ref": ln.ref, "raw_path": rel(raw_path), "provider": r.provider.name, "model": r.provider.model,
            "voice": ln.voice, "style": ln.style, "text": ln.text, "fell_back": r.fell_back,
            "batch": rel(r.output), "batch_span_s": [round(edges[i], 3), round(edges[i + 1], 3)],
            "created_at": now_iso(),
        })
        out[ln.ref] = key
    return out


# ---------------------------------------------------------------------------------------------
# free-tier bookkeeping

def last_quota_reset(now: datetime | None = None) -> datetime:
    """Gemini daily limits reset at midnight Pacific time (11:00 EAT in winter)."""
    try:
        from zoneinfo import ZoneInfo

        pacific = ZoneInfo("America/Los_Angeles")
    except Exception:  # noqa: BLE001 - no tz database on this machine: PST
        pacific = timezone(timedelta(hours=-8))
    now = (now or datetime.now(timezone.utc)).astimezone(pacific)
    return datetime.combine(now.date(), dtime(0, 0), tzinfo=pacific)


def requests_today(model: str, log_path: Path | None = None) -> int:
    """Model calls (failed ones too: they count against the quota) since the last daily reset."""
    since = last_quota_reset()
    return sum(1 for r in read_log(log_path)
               if r.get("event") == "model_call" and r.get("model") == model
               and datetime.fromisoformat(r["ts"]) >= since)


def quota_note(provider: Any, needed: int) -> str:
    rpd = provider.params.get("rpd")
    used = requests_today(provider.model)
    left = f"{max(int(rpd) - used, 0)} of {rpd} left" if rpd else "daily limit unknown"
    warn = " [bold red]- not enough[/bold red]" if rpd and needed > int(rpd) - used else ""
    return f"{provider.model}: this run needs {needed} request(s); runs.jsonl shows {used} used today, {left}{warn}"


# ---------------------------------------------------------------------------------------------
# timing

def build_timing(sb: dict, current: dict[str, dict]) -> dict:
    """timing.json from the takes in use. Echo lines get an entry too (the source's audio and
    duration), so the timeline can look up every line index."""
    shots: dict[str, list[dict]] = {}
    en_words = en_s = am_s = 0.0
    n_lines = 0
    for shot in sb["shots"]:
        sid = shot["id"]
        entries = []
        for i, line in enumerate(shot.get("narration") or []):
            if "echo_of" in line:
                src = current[line["echo_of"]]
                entries.append({"line_idx": i, "echo_of": line["echo_of"], "voice": src["role"],
                                "path": src["path"], "duration_s": src["duration_s"],
                                "gain_db": line.get("gain_db", -8), "reverb": bool(line.get("reverb", False))})
                continue
            cur = current[f"{sid}:{i}"]
            words = len(line["text"].split())
            d = cur["duration_s"]
            entries.append({"line_idx": i, "voice": line["voice"], "voice_name": cur["voice"],
                            "lang": line.get("lang", "en"), "path": cur["path"], "raw_path": cur["raw_path"],
                            "duration_s": d, "words": words, "wps": round(words / d, 3) if d else None,
                            "model": cur["model"], "cache_key": cur["cache_key"]})
            n_lines += 1
            if line.get("lang", "en") == "en":
                en_words += words
                en_s += d
            else:
                am_s += d
        shots[sid] = entries
    return {"stage_version": STAGE_VERSION, "shots": shots,
            "totals": {"lines": n_lines, "english_words": int(en_words), "english_s": round(en_s, 3),
                       "english_wps": round(en_words / en_s, 3) if en_s else None,
                       "amharic_s": round(am_s, 3), "speech_s": round(en_s + am_s, 3)}}


# ---------------------------------------------------------------------------------------------
# the stage

def _forced(line: Line, force: list[str] | None) -> bool:
    return force is not None and (not force or line.shot_id in force or line.ref in force)


def run_narration(profile: str | None = None, *, only: list[str] | None = None, force: list[str] | None = None,
                  dry_run: bool = False, batch_lines: int | None = None, sb: dict | None = None,
                  chain: Any = None, console: Any = None) -> dict:
    from rich.console import Console

    console = console or Console()
    sb = sb if sb is not None else sbm.load_storyboard()
    report = sbm.validate(sb)  # structure only; the duration check runs once timing is written
    if not report.ok:
        raise StoryboardInvalid("storyboard.json is invalid:\n  " + "\n  ".join(report.errors))
    chain = chain if chain is not None else registry.get_provider("tts", profile)
    providers = list(getattr(chain, "providers", chain))
    primary = providers[0]
    batch_lines = int(batch_lines or primary.params.get("batch_lines", DEFAULT_BATCH_LINES))
    takes, manifest = Takes(), Manifest(STAGE)

    lines = plan_lines(sb)
    keys: dict[str, str] = {}
    pending: list[Line] = []
    for ln in lines:
        selected = not only or ln.shot_id in only or ln.ref in only
        key = line_key(ln, primary)
        hit = takes.get(key)
        if hit is None and not _forced(ln, force):
            # a take from a fallback model that is already in use stays in use
            cur = manifest.get(ln.ref) or {}
            for p in providers[1:]:
                k2 = line_key(ln, p)
                if cur.get("cache_key") == k2 and takes.get(k2):
                    key, hit = k2, takes.get(k2)
                    break
        if hit is not None and not (_forced(ln, force) and selected):
            keys[ln.ref] = key
            log_event("cache_hit", stage=STAGE, shot_id=ln.ref, provider=hit["provider"], model=hit["model"],
                      cache_key=key, output=hit["raw_path"])
        elif selected:
            pending.append(ln)

    batches = make_batches(pending, batch_lines)
    console.print(f"narration: {len(lines)} lines, {len(keys)} cache hit(s), {len(pending)} to synthesize "
                  f"in {len(batches)} request(s) (up to {batch_lines} lines per request)")
    for b in batches:
        console.print(f"  request: {b[0].voice} <- {', '.join(ln.ref for ln in b)}")
    if batches:
        console.print("  " + quota_note(primary, len(batches)))
    if dry_run:
        return {"status": "dry_run", "lines": len(lines), "hits": len(keys), "pending": [ln.ref for ln in pending],
                "requests": len(batches)}

    for b in batches:
        keys.update(synthesize(b, providers, takes))

    missing = [ln.ref for ln in lines if ln.ref not in keys]
    current: dict[str, dict] = {}
    for ln in lines:
        if ln.ref not in keys:
            continue
        key = keys[ln.ref]
        take = takes.get(key)
        path, duration = trimmed(take)
        cur = manifest.get(ln.ref)
        if not cur or cur.get("cache_key") != key or cur.get("path") != rel(path):
            manifest.put(ln.ref, cache_key=key, path=path, provider=take["provider"], model=take["model"],
                         raw_path=take["raw_path"], voice=take["voice"], duration_s=duration,
                         fell_back=take.get("fell_back", False))
        current[ln.ref] = {**take, "path": rel(path), "duration_s": duration, "cache_key": key, "role": ln.role}
    for stale in [ref for ref in manifest.entries if ref not in {ln.ref for ln in lines}]:
        del manifest.entries[stale]  # a line that no longer exists in the storyboard
        manifest.save()

    result = {"status": "ok", "lines": len(lines), "generated": len(pending), "requests": len(batches),
              "missing": missing, "timing": None}
    if missing:
        console.print(f"[yellow]timing.json not written: {len(missing)} line(s) have no audio yet "
                      f"({', '.join(missing)}); run without --only[/yellow]")
        return result
    timing = build_timing(sb, current)
    atomic_write_json(sbm.TIMING, timing)
    result["timing"] = rel(sbm.TIMING)
    fell = [ref for ref, c in current.items() if c.get("model") != primary.model]
    if fell:
        console.print(f"[yellow]{len(fell)} line(s) use a fallback model ({', '.join(fell)}); "
                      f"`--force` them when {primary.model} has quota again[/yellow]")
    tl = sbm.timeline(sb, timing)
    full = sbm.validate(sb, timing=timing)
    t = timing["totals"]
    console.print(f"timing.json: {t['english_words']} English words in {t['english_s']:.1f}s "
                  f"({t['english_wps']} words/s), Amharic {t['amharic_s']:.1f}s; "
                  f"film {tl['total_s']:.1f}s incl. end card")
    for e in full.errors:
        console.print(f"[red]error[/red] {e}")
    result.update(total_s=tl["total_s"], errors=full.errors)
    return result


# ---------------------------------------------------------------------------------------------
# the audition

def _short(model: str) -> str:
    return model.replace("gemini-", "").replace("-tts", "")


def run_audition(role: str, *, profile: str | None = None, model: str | None = None,
                 voices: list[str] | None = None, refs: list[str] | None = None, no_style: bool = False,
                 dry_run: bool = False, sb: dict | None = None, chain: Any = None, console: Any = None) -> dict:
    from rich.console import Console
    from rich.table import Table

    console = console or Console()
    sb = sb if sb is not None else sbm.load_storyboard()
    if role not in (sb.get("voices") or {}):
        raise StoryboardInvalid(f"no voice role {role!r} in storyboard.voices (have: {sorted(sb.get('voices') or {})})")
    chain = chain if chain is not None else registry.get_provider("tts", profile)
    providers = list(getattr(chain, "providers", chain))
    if model:
        matches = [p for p in providers if p.model == model]
        if not matches:
            raise ValueError(f"{model!r} is not in the tts chain ({[p.model for p in providers]})")
        provider = matches[0]
    else:
        provider = providers[0]
    cfg = sb["voices"][role]
    candidates = voices or cfg.get("candidates") or [cfg["voice"]]
    refs = refs or AUDITION_LINES.get(role)
    tag = _short(provider.model) + ("-nostyle" if no_style else "")
    out_dir = OUT / "audition" / role / tag
    takes = Takes()

    plans = {v: plan_lines(sb, roles=[role], refs=refs, voice_override=v, no_style=no_style) for v in candidates}
    if not any(plans.values()):
        raise StoryboardInvalid(f"no {role} lines match {refs}")
    todo = {v: [ln for ln in lines if takes.get(line_key(ln, provider)) is None] for v, lines in plans.items()}
    requests = sum(1 for v in todo if todo[v])
    console.print(f"audition {role} on {provider.model}{' without style' if no_style else ''}: "
                  f"{len(candidates)} voice(s) x {len(next(iter(plans.values())))} line(s); {requests} request(s)")
    if requests:
        console.print("  " + quota_note(provider, requests))
    if dry_run:
        return {"status": "dry_run", "requests": requests}

    rows, sheet = [], []
    for v, lines in plans.items():
        if todo[v]:
            synthesize(todo[v], [provider], takes)  # one request per voice, no fallback
        clips, per_line = [], []
        for ln in lines:
            key = line_key(ln, provider)
            take = takes.get(key)
            if ln not in todo[v]:
                log_event("cache_hit", stage=STAGE, shot_id=ln.ref, provider=provider.name, model=provider.model,
                          cache_key=key, output=take["raw_path"], audition=role)
            path, d = trimmed(take)
            clips.append(audio.read_wav(path))
            per_line.append({"ref": ln.ref, "path": rel(path), "duration_s": d, "words": ln.words,
                             "lang": ln.lang, "style": ln.style, "cache_key": key})
        joined = audio.concat(clips, LINE_GAP_S)
        voice_path = out_dir / f"{v}.wav"
        atomic_write_bytes(voice_path, audio.wav_bytes(joined))
        sheet.append(joined)
        en = [x for x in per_line if x["lang"] == "en"]
        en_s = sum(x["duration_s"] for x in en)
        rows.append({"voice": v, "path": rel(voice_path), "lines": per_line,
                     "speech_s": round(sum(x["duration_s"] for x in per_line), 3),
                     "english_wps": round(sum(x["words"] for x in en) / en_s, 3) if en_s else None})
    sheet_path = out_dir / "sheet.wav"
    atomic_write_bytes(sheet_path, audio.wav_bytes(audio.concat(sheet, VOICE_GAP_S)))
    summary = {"role": role, "model": provider.model, "no_style": no_style, "order": candidates,
               "sheet": rel(sheet_path), "voices": rows, "created_at": now_iso(), "run_id": get_run().run_id}
    atomic_write_json(out_dir / "audition.json", summary)

    table = Table(title=f"audition: {role} ({tag})")
    for col in ("voice", "speech s", "English words/s", "file"):
        table.add_column(col)
    for r in rows:
        table.add_row(r["voice"], f"{r['speech_s']:.2f}", str(r["english_wps"] or "-"), r["path"])
    console.print(table)
    console.print(f"Listen: {rel(sheet_path)} (voices in this order: {', '.join(candidates)}, "
                  f"{VOICE_GAP_S}s apart). Choose with storyboard.json voices.{role}.voice")
    return summary


# ---------------------------------------------------------------------------------------------
# the check: hear every line back

VERIFY_VERSION = 1
VERIFY_THRESHOLD = 0.8
LANG_NAMES = {"en": "English", "am": "Amharic, written in Ge'ez script"}
TRANSCRIPT_SCHEMA = {"type": "object", "properties": {"transcript": {"type": "string"}}, "required": ["transcript"]}


def transcribe_prompt(lang: str) -> str:
    return (f"Transcribe exactly what is said in this audio clip, word for word, in the language spoken "
            f"({LANG_NAMES.get(lang, lang)}). Do not translate, correct, complete or explain it. "
            f"If the clip starts or ends in the middle of a sentence, transcribe only what is audible. "
            f"Return JSON: {{\"transcript\": \"...\"}}")


def similarity(expected: str, got: str, lang: str = "en") -> float:
    """1.0 = the same words. English: word sequence; Amharic: letter sequence (spacing varies)."""
    import difflib
    import unicodedata

    def norm(text: str) -> list[str]:
        text = "".join(ch for ch in unicodedata.normalize("NFC", text.lower())
                       if ch.isalnum() or ch.isspace())
        return list(text.replace(" ", "")) if lang != "en" else text.split()

    a, b = norm(expected), norm(got)
    if not a and not b:
        return 1.0
    return round(difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 3)


def edges_ok(expected: str, got: str, min_ratio: float = 0.7) -> bool:
    """Do the first and the last word match? A cut in the wrong pause moves words across the
    boundary (s07 lost "Then... silence." to s08 in the first full run), which a whole-line
    score barely notices; the edges show it at once."""
    import difflib

    def words(text: str) -> list[str]:
        return "".join(ch for ch in text.lower() if ch.isalnum() or ch.isspace()).split()

    e, g = words(expected), words(got)
    if not e or not g:
        return not e and not g
    close = lambda x, y: difflib.SequenceMatcher(None, x, y).ratio() >= min_ratio  # noqa: E731
    return close(e[0], g[0]) and close(e[-1], g[-1])


def _hear(wav: bytes, lang: str, ref: str, providers: list[Any], store: dict, store_path: Path) -> str:
    """Transcript of one clip, cached by the clip's bytes (the same audio is never sent twice)."""
    vkey = cache_key(stage="narration_check", stage_version=VERIFY_VERSION, provider="any", model="any",
                     inputs={"audio_sha": sha256_bytes(wav), "prompt": transcribe_prompt(lang)})
    if vkey in store:
        return store[vkey]["transcript"]
    r = invoke(providers, lambda p: p.generate_json(transcribe_prompt(lang), TRANSCRIPT_SCHEMA,
                                                    attachments=[(wav, "audio/wav")]),
               stage="narration_check", shot_id=ref, input_hash=sha256_bytes(wav), max_attempts=2)
    got = str(r.value.data.get("transcript", "")).strip()
    store[vkey] = {"ref": ref, "transcript": got, "model": r.provider.model, "checked_at": now_iso()}
    atomic_write_json(store_path, store)
    return got


def _check_rows(sb: dict, timing: dict, providers: list[Any], store: dict, store_path: Path) -> list[dict]:
    by_id = {s["id"]: s for s in sb["shots"]}
    rows = []
    for sid, entries in timing["shots"].items():
        for e in entries:
            if "echo_of" in e:
                continue
            line = by_id[sid]["narration"][e["line_idx"]]
            ref, lang = f"{sid}:{e['line_idx']}", line.get("lang", "en")
            got = _hear((ROOT / e["path"]).read_bytes(), lang, ref, providers, store, store_path)
            sim = similarity(line["text"], got, lang)
            # Machine transcription of Amharic is unreliable (EXPERIMENTS.md E18), so for other
            # languages the score is shown only and a native speaker decides by ear.
            edges = edges_ok(line["text"], got) if lang == "en" else None
            rows.append({"ref": ref, "lang": lang, "expected": line["text"], "transcript": got, "similarity": sim,
                         "edges_ok": edges, "take": e["cache_key"],
                         "ok": (sim >= VERIFY_THRESHOLD and bool(edges)) or lang != "en",
                         "informational": lang != "en"})
    return rows


def repair_cuts(bad: list[str], sb: dict, providers: list[Any], store: dict, store_path: Path,
                console: Any, max_candidates: int = 6) -> list[dict]:
    """For each failing line that came from a batch, try the other pauses around its two cuts:
    re-slice the saved response (no TTS call), hear both neighbours back, keep the best cut."""
    takes = Takes()
    current = Manifest(STAGE)
    texts = {f"{s['id']}:{i}": ln for s in sb["shots"] for i, ln in enumerate(s.get("narration") or [])}
    repairs, done = [], set()
    for ref in bad:
        cur = current.get(ref)
        take = takes.entries.get(cur["cache_key"]) if cur else None
        if not take or not take.get("batch"):
            continue
        report_path = (ROOT / take["batch"]).with_suffix(".json")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        refs = [x["ref"] for x in report["lines"]]
        i = refs.index(ref)
        for j in (i - 1, i):  # the cut before and the cut after this line
            if j < 0 or j + 1 >= len(refs) or (str(report_path), j) in done:
                continue
            done.add((str(report_path), j))
            a_ref, b_ref = refs[j], refs[j + 1]
            ka, kb = current.get(a_ref)["cache_key"], current.get(b_ref)["cache_key"]
            ea, eb = takes.entries[ka], takes.entries[kb]
            lo, now_cut, hi = ea["batch_span_s"][0], ea["batch_span_s"][1], eb["batch_span_s"][1]
            clip = audio.read_wav(ROOT / take["batch"])
            pauses = [(x, y) for x, y in report["silences"] if lo < x and y < hi and y - x >= 0.3]
            cands = sorted({round((x + y) / 2, 3) for x, y in pauses} | {now_cut},
                           key=lambda c: abs(c - now_cut))[:max_candidates + 1]

            def score(cut: float) -> tuple[float, dict]:
                out = {}
                for r_, span in ((a_ref, (lo, cut)), (b_ref, (cut, hi))):
                    piece, _, _ = audio.trim(clip.slice(*span))
                    lang = texts[r_].get("lang", "en")
                    got = _hear(audio.wav_bytes(piece), lang, r_, providers, store, store_path)
                    out[r_] = similarity(texts[r_]["text"], got, lang)
                return sum(out.values()), out

            scored = {c: score(c) for c in cands}
            best = max(scored, key=lambda c: (scored[c][0], -abs(c - now_cut)))
            if best == now_cut or scored[best][0] <= scored[now_cut][0]:
                continue
            for k, e, span in ((ka, ea, (lo, best)), (kb, eb, (best, hi))):
                atomic_write_bytes(ROOT / e["raw_path"], audio.wav_bytes(clip.slice(*span)))
                e["batch_span_s"] = [round(span[0], 3), round(span[1], 3)]
                takes.put(k, {**e, "repaired": True})
            rec = {"between": [a_ref, b_ref], "from_s": now_cut, "to_s": best,
                   "scores_before": scored[now_cut][1], "scores_after": scored[best][1], "at": now_iso()}
            report.setdefault("repairs", []).append(rec)
            report["split"]["cuts"][j] = best
            atomic_write_json(report_path, report)
            repairs.append(rec)
            console.print(f"repaired the cut between {a_ref} and {b_ref}: {now_cut:.2f}s -> {best:.2f}s "
                          f"(heard back: {scored[now_cut][1]} -> {scored[best][1]})")
    return repairs


def run_verify(profile: str | None = None, *, force: bool = False, repair: bool = True, sb: dict | None = None,
               timing: dict | None = None, chain: Any = None, console: Any = None) -> dict:
    """Hear every line back: transcribe its take with a text model and compare with the storyboard
    text. Catches a wrong cut in a batch (a word in the wrong line) or a skipped / invented word,
    and repairs a wrong cut from the saved response (no new TTS call). Transcripts are cached by
    audio, so a clip is heard once until it changes; `--force` hears everything again."""
    from rich.console import Console
    from rich.table import Table

    console = console or Console()
    sb = sb if sb is not None else sbm.load_storyboard()
    timing = timing if timing is not None else sbm.load_timing()
    if timing is None:
        raise StoryboardInvalid("no timing.json yet: run `make narration` first")
    chain = chain if chain is not None else registry.get_provider("transcribe", profile)
    providers = list(getattr(chain, "providers", chain))
    store_path = OUT / "verify.json"
    store = {} if force or not store_path.exists() else json.loads(store_path.read_text(encoding="utf-8"))
    rows = _check_rows(sb, timing, providers, store, store_path)
    repairs = []
    bad = [r["ref"] for r in rows if not r["ok"]]
    if bad and repair:
        repairs = repair_cuts(bad, sb, providers, store, store_path, console)
        if repairs:  # the trims and timing.json follow the new cuts; no TTS call
            run_narration(profile, sb=sb, console=console)
            timing = sbm.load_timing()
            rows = _check_rows(sb, timing, providers, store, store_path)
    table = Table(title="narration check: each line heard back")
    for col in ("line", "sim", "transcript"):
        table.add_column(col)
    for row in rows:
        mark = "[red]" if not row["ok"] else ("[dim]" if row["informational"] else "")
        table.add_row(row["ref"], f"{mark}{row['similarity']:.2f}", row["transcript"])
    console.print(table)
    bad = [row["ref"] for row in rows if not row["ok"]]
    info = [row["ref"] for row in rows if row["informational"]]
    console.print(f"{len(rows) - len(bad)}/{len(rows)} lines pass (English: similarity >= {VERIFY_THRESHOLD} "
                  f"and first/last words match; "
                  f"{', '.join(info) or 'none'}: judged by ear, score shown only)"
                  + (f"; [red]check: {', '.join(bad)}[/red]" if bad else ""))
    atomic_write_json(OUT / "verify_report.json", {"rows": rows, "repairs": repairs, "checked_at": now_iso(),
                                                   "threshold": VERIFY_THRESHOLD})
    return {"rows": rows, "bad": bad, "repairs": repairs}
