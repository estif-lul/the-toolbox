"""The WAV tools behind batching: silence detection, trimming, and cutting one response into lines."""

import array
import math

import pytest

from pipeline.common import audio

RATE = 8000


def tone(seconds: float, amp: int = 8000, freq: float = 220.0) -> audio.Clip:
    n = int(seconds * RATE)
    return audio.Clip(array.array("h", (int(amp * math.sin(2 * math.pi * freq * i / RATE)) for i in range(n))), RATE)


def quiet(seconds: float) -> audio.Clip:
    return audio.silence(seconds, RATE)


def joined(*parts: audio.Clip) -> audio.Clip:
    return audio.concat(list(parts))


def test_wav_roundtrip():
    clip = joined(quiet(0.1), tone(0.3))
    back = audio.read_wav(audio.wav_bytes(clip))
    assert back.rate == RATE and back.samples == clip.samples


def test_silences_and_bounds():
    clip = joined(quiet(0.5), tone(1.0), quiet(0.8), tone(0.5), quiet(0.3))
    env = audio.envelope_db(clip)
    assert audio.speech_bounds(env) == (0.5, 2.8)
    sil = audio.find_silences(env)
    assert sil[0] == (0.0, 0.5) and (1.5, 2.3) in sil


def test_trim_keeps_a_margin_and_never_clips_speech():
    clip = joined(quiet(0.6), tone(1.0), quiet(0.9))
    out, start, end = audio.trim(clip)
    assert start == pytest.approx(0.6 - audio.KEEP_BEFORE_S)
    assert abs(end - (1.6 + audio.KEEP_AFTER_S)) < 0.011
    assert abs(out.duration_s - (1.0 + audio.KEEP_BEFORE_S + audio.KEEP_AFTER_S)) < 0.011


def test_an_isolated_click_is_not_speech():
    click = tone(0.01, amp=120)  # about -49 dBFS, just above the silence threshold
    clip = joined(tone(0.6), quiet(1.2), click, quiet(2.2), tone(1.0))
    env = audio.envelope_db(clip)
    assert (0.6, 4.01) in audio.find_silences(env)
    out, start, end = audio.trim(joined(tone(0.6), quiet(1.2), click, quiet(1.0)))
    assert end == pytest.approx(0.6 + audio.KEEP_AFTER_S, abs=0.011)


def test_split_prefers_long_pauses_that_match_the_text():
    # three lines of 2 s, 1 s, 3 s; line 3 has a 0.6 s dramatic pause inside it
    clip = joined(quiet(0.3), tone(2.0), quiet(1.4), tone(1.0), quiet(1.3), tone(1.2), quiet(0.6), tone(1.8), quiet(0.3))
    env = audio.envelope_db(clip)
    res = audio.split_points(audio.find_silences(env), audio.speech_bounds(env), [20, 10, 30])
    assert res.ok, res.problems
    assert res.cuts == pytest.approx([3.0, 5.35], abs=0.011)
    assert res.boundary_pauses == [1.4, 1.3]


def test_split_refuses_when_a_line_is_missing():
    clip = joined(quiet(0.3), tone(2.0), quiet(1.4), tone(1.0), quiet(0.3))
    env = audio.envelope_db(clip)
    res = audio.split_points(audio.find_silences(env), audio.speech_bounds(env), [20, 10, 30])
    assert not res.ok and "pause" in res.problems[0]


def test_split_flags_lengths_that_do_not_match_the_text():
    # the model read line 2 far too long relative to its text: the split is not trusted
    clip = joined(quiet(0.3), tone(1.0), quiet(1.4), tone(6.0), quiet(0.3))
    env = audio.envelope_db(clip)
    res = audio.split_points(audio.find_silences(env), audio.speech_bounds(env), [30, 5])
    assert not res.ok and any("expected length" in p for p in res.problems)


def test_single_line_needs_no_split():
    res = audio.split_points([], (0.1, 2.0), [12])
    assert res.ok and res.cuts == [] and res.segments == [(0.1, 2.0)]


def test_text_weight_counts_letters_and_pauses():
    assert audio.text_weight("Then… silence.") > audio.text_weight("Then silence")
    assert audio.text_weight("ጎበዝ ልጄ") == 5
