import pytest

from pipeline.common.retry import FatalError
from pipeline.providers import base, registry
from pipeline.providers.kenburns import MOVES, zoompan_filter

PROTOCOL = {
    "text": base.TextProvider, "tts": base.TTSProvider, "image": base.ImageProvider,
    "video": base.VideoProvider, "music": base.MusicProvider,
}


@pytest.mark.parametrize("profile", ["free", "paid"])
def test_every_configured_adapter_builds_and_matches_its_protocol(profile):
    cfg = registry.load_config()
    for stage, entries in cfg["profiles"][profile].items():
        chain = registry.get_provider(stage, profile, cfg)
        assert len(chain.providers) == len(entries) >= 1
        for p in chain:
            assert p.model and p.name
            if stage in PROTOCOL and p.name != "kenburns":
                assert isinstance(p, PROTOCOL[stage]), (stage, p)


def test_video_chain_always_ends_in_ken_burns():
    for profile in ("free", "paid"):
        assert registry.get_provider("video", profile).providers[-1].name == "kenburns"


def test_paid_stub_fails_loudly_with_pointer():
    p = registry.get_provider("image", "paid").primary
    with pytest.raises(FatalError, match="PAID_LANE.md"):
        p.generate("x", 1, 64, 64)


def test_unknown_profile_and_stage():
    with pytest.raises(KeyError):
        registry.get_provider("text", "nope")
    with pytest.raises(KeyError):
        registry.get_provider("nope", "free")


@pytest.mark.parametrize("move", MOVES)
def test_kenburns_filter_for_every_move(move):
    vf = zoompan_filter(move, 0.08, frames=48, size=1024, fps=24)
    assert vf.startswith("scale=4096:4096") and "zoompan=" in vf and "d=48" in vf and "s=1024x1024" in vf
    # commas inside expressions would split the filtergraph
    z = vf.split("zoompan=")[1].split(",setsar")[0]
    assert z.count(",") == 0


def test_kenburns_rejects_unknown_move():
    with pytest.raises(ValueError):
        zoompan_filter("spin", 0.1, 10, 64, 24)
