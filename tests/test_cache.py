from pipeline.common import cache
from pipeline.common.cache import Manifest, cache_key, canonical_json


def narration_key(shot: dict, voice: dict) -> str:
    """What the narration stage will do: key only on the fields it uses."""
    return cache_key(stage="narration", stage_version=1, provider="gemini_tts", model="m",
                     params={"voice": voice["voice"], "style": voice["style"]}, seed=None,
                     inputs={"text": shot["text"]})


def test_canonical_json_is_order_independent_and_keeps_unicode():
    a = {"b": 1, "a": {"y": [1, 2], "x": "እስኪ እንየው"}}
    b = {"a": {"x": "እስኪ እንየው", "y": [1, 2]}, "b": 1}
    assert canonical_json(a) == canonical_json(b)
    assert "እስኪ" in canonical_json(a)
    assert " " not in canonical_json({"k": [1, 2]})


def test_key_stable_across_dict_ordering():
    k1 = cache_key(stage="s", stage_version=1, provider="p", model="m", params={"a": 1, "b": 2},
                   seed=7, inputs={"x": 1, "y": 2}, upstream_hashes={"img": "abc"})
    k2 = cache_key(stage="s", stage_version=1, provider="p", model="m", params={"b": 2, "a": 1},
                   seed=7, inputs={"y": 2, "x": 1}, upstream_hashes={"img": "abc"})
    assert k1 == k2 and len(k1) == 64


def test_irrelevant_field_keeps_key_relevant_field_changes_it():
    voice = {"voice": "Kore", "style": "warm"}
    shot = {"text": "My dad never called anyone.", "image_prompt": "a red toolbox"}
    base = narration_key(shot, voice)
    assert narration_key({**shot, "image_prompt": "a blue toolbox"}, voice) == base  # not used by TTS
    assert narration_key({**shot, "text": "My dad fixed everything."}, voice) != base
    assert narration_key(shot, {**voice, "style": "slow"}) != base


def test_every_key_component_matters():
    base = dict(stage="s", stage_version=1, provider="p", model="m", params={}, seed=1, inputs={},
                upstream_hashes={})
    k = cache_key(**base)
    for field, value in [("stage_version", 2), ("provider", "q"), ("model", "n"), ("seed", 2),
                         ("params", {"steps": 4}), ("inputs", {"t": 1}), ("upstream_hashes", {"f": "x"})]:
        assert cache_key(**{**base, field: value}) != k, field


def test_manifest_freshness(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "ROOT", tmp_path)
    art = tmp_path / "outputs" / "narration" / "s05" / "abc.wav"
    art.parent.mkdir(parents=True)
    art.write_bytes(b"RIFF....")
    m = Manifest("narration", root=tmp_path / "outputs")
    m.put("s05", cache_key="k1", path=art, provider="gemini_tts", model="m")
    again = Manifest("narration", root=tmp_path / "outputs")  # reloaded from disk
    assert again.is_fresh("s05", "k1")
    assert not again.is_fresh("s05", "k2")          # key changed -> regenerate
    assert not again.is_fresh("s06", "k1")          # never generated
    art.write_bytes(b"tampered")
    assert again.is_fresh("s05", "k1")
    assert not again.is_fresh("s05", "k1", verify_hash=True)
    art.unlink()
    assert not again.is_fresh("s05", "k1")          # file gone -> regenerate


def test_artifact_path_layout():
    p = cache.artifact_path("keyframes", "s05", "0123456789abcdef" * 4, ".png")
    assert p.parts[-3:] == ("keyframes", "s05", "0123456789abcdef.png")
