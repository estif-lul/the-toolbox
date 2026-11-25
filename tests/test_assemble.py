"""Radio-cut filter graphs are built from the timeline and the storyboard's duck settings."""

from pipeline import assemble, music


def test_stem_places_each_line_and_echoes_with_reverb():
    items = [assemble.Placement("a.wav", 0.8), assemble.Placement("b.wav", 12.345, -8.0, True)]
    f = assemble.stem_filter(items, 80.0)
    assert "[0:a]aformat=sample_fmts=fltp:channel_layouts=mono,adelay=800:all=1[n0]" in f
    assert "volume=-8.0dB," + assemble.ECHO_FILTER + ",adelay=12345:all=1[n1]" in f
    assert "amix=inputs=2:normalize=0" in f and "apad=whole_dur=80.000" in f
    args = assemble.stem_args(items, 80.0, assemble.CUTS / "narration_stem.wav")
    assert args[:4] == ["-i", "a.wav", "-i", "b.wav"] and args[-1] == "outputs/cuts/narration_stem.wav"


def test_mix_ducks_the_pad_under_the_voice_with_storyboard_values():
    duck = {"threshold": 0.02, "ratio": 6, "attack_ms": 300, "release_ms": 1500}
    f = assemble.mix_filter(duck, 3.5, -12.25, 80.0)
    assert "[pad][sc]sidechaincompress=threshold=0.02:ratio=6:attack=300:release=1500[ducked]" in f
    assert "volume=3.50dB" in f and "volume=-12.25dB" in f
    assert "[ducked][v]amix=inputs=2:normalize=0" in f


def test_loudnorm_second_pass_uses_the_measurement():
    m = {"input_i": "-20.1", "input_tp": "-3.2", "input_lra": "6.0", "input_thresh": "-30.5", "target_offset": "0.3"}
    f = assemble.loudnorm_filter(m)
    assert f.startswith("loudnorm=I=-14.0:TP=-1.0:LRA=11.0:measured_I=-20.1")
    assert "linear=true" in f
    stderr = 'noise\n[Parsed_loudnorm_0 @ 0x1]\n{\n\t"input_i" : "-20.10",\n\t"input_tp" : "-3.2"\n}\n'
    assert assemble.parse_loudnorm(stderr)["input_i"] == "-20.10"


def test_placeholder_pad_is_labelled_and_sized_to_the_film():
    args = music.placeholder_args(81.37, music.artifact_path("music", "placeholder", "ab" * 32, "flac"))
    src = args[args.index("-i") + 1]
    assert src.startswith("aevalsrc=exprs='") and ":d=81.37" in src
    assert "afade=t=out:st=78.37:d=3" in args[args.index("-af") + 1]
