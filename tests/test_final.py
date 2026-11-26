"""The final edit's pure parts: transitions keep every shot on its timeline time, the join graph,
split-screen subtitle placement in 9:16, the hold length, the mix filter and the QC checks."""

from pipeline import assemble
from pipeline.common.subtitles import Cue

from test_schema import minimal_storyboard

FPS = assemble.FPS


def test_transitions_map_each_kind():
    sb = minimal_storyboard(4)
    for shot, kind in zip(sb["shots"], ["fade_from_black", "crossfade", "dip_to_black", "cut"]):
        shot["transition_in"] = kind
    counts = [100, 100, 100, 100, 72]                     # 4 shots + the end card
    tr = assemble.transitions(sb, counts)
    xf = round(assemble.CROSSFADE_S * FPS)
    assert tr[0]["fade_in"] == assemble.FADE_FIRST_S
    assert tr[1]["xfade"] and tr[0]["extra"] == xf          # the outgoing shot is lengthened
    assert tr[2]["fade_in"] == assemble.DIP_S and tr[1]["fade_out"] == assemble.DIP_S
    assert not tr[3]["xfade"] and tr[3]["fade_in"] == 0
    assert tr[4]["fade_in"] == assemble.DIP_S and tr[3]["fade_out"] == assemble.DIP_S   # into the end card


def test_join_offsets_are_timeline_starts():
    segs = [{"frames": 100}, {"frames": 120, "xfade": True}, {"frames": 50}, {"frames": 72, "xfade": True}]
    g = assemble.join_filters(segs)
    assert f"offset={100 / FPS:.4f}" in g                   # s1 starts at frame 100
    assert f"offset={270 / FPS:.4f}" in g                   # s3 starts at 100 + 120 + 50
    assert "[j1][s2]concat=n=2" in g and g.endswith("[cat]")


def test_single_segment_join():
    assert assemble.join_filters([{"frames": 10}]) == "[s0]null[cat]"


def test_fades_and_overlap_in_the_video_graph(tmp_path):
    segs = [{"kind": "clip", "inputs": ["a.mp4"], "focus": [None], "frames": 96, "fade_in": 0.8, "extra": 12},
            {"kind": "clip", "inputs": ["b.mp4"], "focus": [None], "frames": 96, "xfade": True, "fade_out": 0.4}]
    graph, n = assemble.final_video_graph(segs, "9x16", tmp_path / "x.srt")
    assert n == 2
    assert "trim=end_frame=108" in graph                    # 96 + the crossfade overlap
    assert "fade=t=in:st=0:d=0.8" in graph and f"fade=t=out:st={96 / FPS - 0.4:.4f}:d=0.4" in graph
    assert "xfade=transition=fade" in graph and "fontsdir=assets/fonts" in graph


def test_split_screen_has_a_divider():
    segs = [{"kind": "split", "inputs": ["a.mp4", "b.mp4"], "focus": [None, None], "frames": 48}]
    v, _ = assemble.segment_filters(segs, "9x16")
    h, _ = assemble.segment_filters(segs, "16x9")
    assert "vstack=inputs=2,drawbox=x=0:y=ih/2-2" in v and "hstack=inputs=2,drawbox=x=iw/2-2" in h


def test_split_screen_subtitles_move_to_the_divider_in_9x16():
    sb = minimal_storyboard(2)
    sb["shots"][1]["layers"] = [{"id": "a"}, {"id": "b"}]
    tl = {"shots": [{"start_s": 0.0, "duration_s": 5.0}, {"start_s": 5.0, "duration_s": 5.0}]}
    cues = [Cue(1.0, 2.0, ["first"]), Cue(5.5, 6.0, ["on the call", "second row"], italic=True)]
    nine = assemble.export_cues(cues, sb, tl, "9x16")
    assert nine[0].rows == ["first"]
    assert nine[1].rows == ["{\\an5}on the call", "second row"] and nine[1].text.startswith("<i>{\\an5}")
    assert assemble.export_cues(cues, sb, tl, "16x9") == cues


def test_hold_amount_is_gentle_and_capped():
    assert assemble.hold_amount(0) == 0
    assert assemble.hold_amount(2.5) == 0.03
    assert assemble.hold_amount(20) == 0.06


def test_final_mix_fades_and_ducks():
    duck = {"threshold": 0.02, "ratio": 6, "attack_ms": 300, "release_ms": 1500}
    f = assemble.final_mix_filter(duck, 1.5, -3.25, 75.7)
    assert "volume=1.50dB" in f and "volume=-3.25dB" in f
    assert "afade=t=in:d=1" in f and "afade=t=out:st=72.700:d=3" in f
    assert "sidechaincompress=threshold=0.02:ratio=6:attack=300:release=1500" in f
    assert assemble.final_loudnorm().startswith("loudnorm=I=-14.0:TP=-1.5")


def test_chosen_music_none_until_chosen():
    sb = minimal_storyboard(2)
    path, why = assemble.chosen_music(sb)
    assert path is None and "placeholder" in why
