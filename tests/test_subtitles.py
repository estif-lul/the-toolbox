"""Subtitle cues: line length limits, timing within the measured span, italics for Dad."""

from pipeline.common import storyboard as sbm
from pipeline.common import subtitles as st

from test_schema import minimal_storyboard


def test_short_line_is_one_row():
    assert st.split_text("And the whole house lit up again.") == [["And the whole house lit up again."]]


def test_rows_are_at_most_40_chars_and_cues_at_most_2_rows():
    text = ("When the power went out, everyone said: call someone. Dad just picked up his tester, "
            "and the whole street watched him work by candlelight.")
    cues = st.split_text(text)
    assert len(cues) >= 2
    for rows in cues:
        assert 1 <= len(rows) <= 2
        assert all(len(r) <= st.MAX_CHARS for r in rows)
    assert " ".join(" ".join(rows) for rows in cues) == " ".join(text.split())


def test_two_rows_break_at_punctuation_when_balanced():
    rows = st.split_text("If it could be done at home, he did it himself.")[0]
    assert rows == ["If it could be done at home,", "he did it himself."]


def test_cue_times_follow_characters_and_minimum_duration():
    cues = st.line_cues("A long first clause that fills a cue, then more words to make a second cue here.", 10.0, 4.0)
    assert cues[0].start == 10.0 and abs(cues[-1].end - 14.0) < 1e-6
    short = st.finalize([st.Cue(1.0, 1.3, ["Hi."]), st.Cue(5.0, 6.0, ["Next."])])
    assert short[0].end == 2.0  # at least 1.0 s on screen
    clipped = st.finalize([st.Cue(1.0, 1.3, ["Hi."]), st.Cue(1.6, 2.6, ["Next."])])
    assert clipped[0].end == round(1.6 - st.GAP_S, 3)  # never into the next cue


def test_build_cues_uses_translation_in_italics_and_echoes():
    sb = minimal_storyboard()
    sb["shots"][0]["narration"].append(
        {"voice": "narrator", "lang": "am", "text": "እስኪ እንየው", "subtitle": "Let's look at it first."})
    sb["shots"][1]["narration"].append({"echo_of": "s01:1", "gain_db": -8, "reverb": True})
    tl = sbm.timeline(sb)
    cues = st.build_cues(sb, tl)
    texts = [c.text for c in cues]
    assert "<i>Let's look at it first.</i>" in texts
    assert texts.count("<i>Let's look at it first.</i>") == 2  # the echo shows the translation too
    assert "እስኪ" not in "".join(texts)
    srt = st.to_srt(cues)
    assert srt.startswith("1\n00:00:")
    assert " --> " in srt


def test_srt_timestamp_format():
    assert st._ts(3725.0429) == "01:02:05,043"


def test_cue_boundaries_snap_to_pauses_in_the_audio():
    text = "A leaking pipe. A wrench. Patience. Then… silence. And more words to need a second cue."
    plain = st.line_cues(text, 0.0, 8.0)
    assert len(plain) == 2
    # the reader's pause sits 1 s earlier than the character split predicts
    pause = (plain[0].end - 1.2, plain[0].end - 0.4)
    snapped = st.line_cues(text, 0.0, 8.0, pauses=[pause])
    assert snapped[0].end == round(pause[0], 3) and snapped[1].start == round(pause[1], 3)
    far = st.line_cues(text, 0.0, 8.0, pauses=[(0.1, 0.3)])  # too far away: ignored
    assert far[0].end == plain[0].end
