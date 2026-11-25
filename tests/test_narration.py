"""The narration stage without network: batching, per-line caching, timing.json, auditions, fallbacks."""

import array
import copy
import io
import math

import pytest
from rich.console import Console

from pipeline import narration
from pipeline.common import audio, cache
from pipeline.common import storyboard as sbm
from pipeline.common.log import read_log
from pipeline.common.retry import QuotaExhaustedError
from pipeline.providers.base import AudioResult

from test_schema import minimal_storyboard

RATE = 8000


def _tone(seconds):
    n = int(seconds * RATE)
    return audio.Clip(array.array("h", (int(9000 * math.sin(2 * math.pi * 200 * i / RATE)) for i in range(n))), RATE)


class FakeTTS:
    name = "fake_tts"

    def __init__(self, model="fake-1", fail_with=None):
        self.model, self.params, self.min_interval_s = model, {"batch_lines": 8}, 0
        self.requests, self.fail_with = [], fail_with

    def _speech(self, texts):
        if self.fail_with:
            raise self.fail_with
        self.requests.append(list(texts))
        parts = [audio.silence(0.3, RATE)]
        for i, t in enumerate(texts):
            if i:
                parts.append(audio.silence(1.2, RATE))
            parts.append(_tone(0.04 * audio.text_weight(t)))
        parts.append(audio.silence(0.3, RATE))
        clip = audio.concat(parts)
        return AudioResult(audio.wav_bytes(clip), RATE, clip.duration_s, {})

    def synthesize(self, text, voice, style=None):
        return self._speech([text])

    def synthesize_batch(self, items, voice):
        return self._speech([t for t, _ in items])


@pytest.fixture
def outputs(tmp_path, monkeypatch, run_log):
    out = tmp_path / "outputs"
    monkeypatch.setattr(cache, "OUTPUTS", out)
    monkeypatch.setattr(narration, "OUT", out / "narration")
    monkeypatch.setattr(narration, "TAKES", out / "narration" / "takes.json")
    monkeypatch.setattr(sbm, "TIMING", out / "narration" / "timing.json")
    return out


def storyboard():
    sb = minimal_storyboard()
    sb["voices"]["dad"]["candidates"] = ["Algenib", "Charon"]
    sb["shots"][1]["narration"].append(
        {"voice": "dad", "lang": "am", "text": "እስኪ እንየው", "subtitle": "Let's look at it first.",
         "style": "Speak in Amharic: calm"})
    sb["shots"][2]["narration"].append({"echo_of": "s02:1", "gain_db": -8, "reverb": True})
    return sb


def quiet():
    return Console(file=io.StringIO())


def run(sb, chain, **kw):
    return narration.run_narration(sb=sb, chain=chain, console=quiet(), **kw)


def test_first_run_batches_by_voice_and_writes_timing(outputs):
    tts = FakeTTS()
    res = run(storyboard(), [tts])
    assert res["requests"] == 2  # 8 narrator lines in one request, Dad's line in another
    assert [len(r) for r in tts.requests] == [8, 1]
    timing = sbm.load_timing(outputs / "narration" / "timing.json")
    s02 = timing["shots"]["s02"]
    assert [e["voice"] for e in s02] == ["narrator", "dad"]
    echo = timing["shots"]["s03"][1]
    assert echo["echo_of"] == "s02:1" and echo["path"] == s02[1]["path"]  # the echo reuses the audio
    for e in timing["shots"]["s01"]:
        assert e["duration_s"] == pytest.approx(0.04 * audio.text_weight(storyboard()["shots"][0]["narration"][0]["text"])
                                                + audio.KEEP_BEFORE_S + audio.KEEP_AFTER_S, abs=0.03)
    sbm.timeline(storyboard(), timing)  # every line index resolves, the echo too


def test_rerun_is_all_cache_hits(outputs, run_log):
    tts = FakeTTS()
    run(storyboard(), [tts])
    tts.requests.clear()
    res = run(storyboard(), [tts])
    assert res["requests"] == 0 and tts.requests == []
    hits = [r for r in read_log(run_log) if r["event"] == "cache_hit"]
    assert len(hits) == 9


def test_editing_one_line_costs_one_request_for_that_line(outputs):
    tts = FakeTTS()
    sb = storyboard()
    run(sb, [tts])
    tts.requests.clear()
    sb2 = copy.deepcopy(sb)
    sb2["shots"][4]["narration"][0]["text"] = "A shorter line for shot five."
    res = run(sb2, [tts])
    assert res["requests"] == 1 and tts.requests == [["A shorter line for shot five."]]


def test_style_and_tts_text_change_the_key_subtitle_does_not(outputs):
    tts = FakeTTS()
    sb = storyboard()
    base = {ln.ref: narration.line_key(ln, tts) for ln in narration.plan_lines(sb)}
    sb["shots"][1]["narration"][1]["subtitle"] = "Let us look first."
    assert {ln.ref: narration.line_key(ln, tts) for ln in narration.plan_lines(sb)} == base
    sb["shots"][1]["narration"][1]["tts_text"] = "Eski, enyew."
    changed = {ln.ref: narration.line_key(ln, tts) for ln in narration.plan_lines(sb)}
    assert [r for r in base if base[r] != changed[r]] == ["s02:1"]


def test_force_one_shot_regenerates_only_it(outputs):
    tts = FakeTTS()
    run(storyboard(), [tts])
    tts.requests.clear()
    res = run(storyboard(), [tts], force=["s03"])
    assert res["requests"] == 1 and len(tts.requests[0]) == 1


def test_audition_on_the_primary_prepays_the_chosen_voice(outputs):
    tts = FakeTTS()
    sb = storyboard()
    summary = narration.run_audition("dad", sb=sb, chain=[tts], console=quiet())
    assert len(tts.requests) == 2  # one request per candidate voice
    assert [v["voice"] for v in summary["voices"]] == ["Algenib", "Charon"]
    tts.requests.clear()
    sb["voices"]["dad"]["voice"] = "Charon"
    res = run(sb, [tts])
    assert res["requests"] == 1 and len(tts.requests[0]) == 8  # only the narrator; Dad was a hit


def test_fallback_take_is_kept_until_forced(outputs):
    dead = FakeTTS("fake-1", fail_with=QuotaExhaustedError("429 per day"))
    lite = FakeTTS("fake-lite")
    res = run(storyboard(), [dead, lite])
    assert res["requests"] == 2 and len(lite.requests) == 2
    lite.requests.clear()
    dead.fail_with = None
    res = run(storyboard(), [dead, lite])
    assert res["requests"] == 0  # the fallback takes stay in use: no surprise quota spend
    res = run(storyboard(), [dead, lite], force=["s01"])
    assert res["requests"] == 1 and len(dead.requests) == 1


def test_split_failure_keeps_the_response_and_saves_no_lines(outputs):
    class Mumbler(FakeTTS):
        def synthesize_batch(self, items, voice):  # drops all pauses: one long blob
            return self._speech([" ".join(t for t, _ in items)])

    with pytest.raises(narration.SplitFailed):
        run(storyboard(), [Mumbler()])
    assert list((outputs / "narration" / "batches").glob("*.wav"))
    assert narration.Takes().entries == {}


def test_dry_run_makes_no_request(outputs):
    tts = FakeTTS()
    res = run(storyboard(), [tts], dry_run=True)
    assert res["requests"] == 2 and tts.requests == []


def test_batches_respect_the_size_limit():
    lines = narration.plan_lines(storyboard())
    batches = narration.make_batches(lines, 3)
    assert [len(b) for b in batches] == [3, 1, 3, 2]
    assert {b[0].voice for b in batches} == {"Achird", "Algenib"}


def test_heard_back_scores():
    assert narration.similarity("My dad never called anyone.", "my dad never called anyone") == 1.0
    assert narration.edges_ok("A wrench. Patience. Then… silence.", "a wrench patience") is False
    assert narration.edges_ok("Years later, he stopped.", "then silence. Years later, he stopped.") is False
    assert narration.edges_ok("From a few planks, he built the rekebot.", "from a few planks he built the rekebot")
