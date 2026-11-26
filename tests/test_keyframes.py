"""Refs and keyframes without network: prompts, which references go where, locking, the budget
guard, contact sheets, recording a choice, and the crop geometry the previews and the edit share."""

import io
import json

import pytest
from PIL import Image
from rich.console import Console

from pipeline import assemble, keyframes
from pipeline.choose import choose
from pipeline.common import cache
from pipeline.common import storyboard as sbm
from pipeline.common.crops import crop_box, export_crop
from pipeline.providers.base import ImageResult

from test_schema import minimal_storyboard


class FakeImage:
    name, model = "fake_image", "fake-klein"

    def __init__(self):
        self.params, self.max_refs, self.min_interval_s, self.calls = {"steps": 4}, 4, 0, []

    def generate(self, prompt, seed, w, h, refs=(), steps=None):
        self.calls.append((prompt, seed, [str(r) for r in refs]))
        buf = io.BytesIO()
        Image.new("RGB", (64, 64), (seed % 255, 80, 40)).save(buf, "JPEG")
        return ImageResult(buf.getvalue(), "image/jpeg", 64, 64, seed, {})


def quiet():
    return Console(file=io.StringIO())


@pytest.fixture
def outputs(tmp_path, monkeypatch, run_log):
    monkeypatch.setattr(cache, "OUTPUTS", tmp_path / "outputs")
    monkeypatch.setattr(keyframes, "neurons_today", lambda log_path=None: 0.0)
    return tmp_path / "outputs"


def storyboard():
    sb = minimal_storyboard()
    sb["characters"] = [
        {"id": "dad", "description": "the father: a man in navy overalls", "seed": 1101, "reference_choice": None},
        {"id": "me_child", "description": "the boy: a boy in a mustard T-shirt", "seed": 1201, "reference_choice": None},
        {"id": "me_teen", "description": "the teenage son: the same boy at fifteen", "seed": 1202,
         "derived_from": "me_child", "reference_choice": None},
    ]
    sb["props"] = [{"id": "toolbox", "description": "the red toolbox: a dented red toolbox"}]
    sb["shots"][0].update(characters=[], props=["toolbox"])
    sb["shots"][1].update(characters=["dad", "me_child"], props=[])
    sb["shots"][2].update(characters=[], props=[])
    return sb


def refs_chosen(sb, outputs):
    img = FakeImage()
    keyframes.run_refs(sb=sb, chain=[img], console=quiet())
    sb["style"]["reference_choice"] = 0
    keyframes.run_refs(sb=sb, chain=[img], console=quiet())
    sb["characters"][0]["reference_choice"] = 1
    sb["characters"][1]["reference_choice"] = 2
    return img


def test_crop_geometry():
    assert crop_box(720, 1280) == (224, 0, 576, 1024)
    assert crop_box(1280, 720) == (0, 224, 1024, 576)
    assert export_crop("16x9", {"x": 0.5, "y": 0.0}) == (0, 0, 1024, 576)       # clamped to the frame
    assert export_crop("9x16", {"x": 0.9, "y": 0.5}) == (448, 0, 576, 1024)
    assert export_crop("9x16", None, half=True) == (0, 56, 1024, 910)            # 720x640 half
    assert export_crop("16x9", None, half=True) == (56, 0, 910, 1024)            # 640x720 half


def test_prompt_recipe_and_reference_sentence():
    sb = storyboard()
    text = keyframes.compose(sb, "Wide shot of the yard", ["dad"], ["toolbox"])
    assert text.startswith("Wide shot of the yard. The father: a man in navy overalls. The red toolbox:")
    assert text.endswith(f"Style: {sb['style']['block']}")
    job = keyframes.Job("keyframes", "s02", 0, 1, text, [("the father", __file__)])
    assert job.prompt(False) == text
    assert "image 1 is the father" in job.prompt(True)
    assert "Keep the art style of the references" in job.prompt(True)  # no style image in this job


def test_refs_wait_for_choices_then_lock(outputs):
    sb = storyboard()
    img = FakeImage()
    res = keyframes.run_refs(sb=sb, chain=[img], console=quiet())
    assert res["generated"] == 4 and any("dad" in w for w in res["waiting"])  # only the style first
    sb["style"]["reference_choice"] = 0
    res = keyframes.run_refs(sb=sb, chain=[img], console=quiet())
    assert res["generated"] == 8  # dad + boy; the teen waits for the boy's choice
    assert any("me_teen" in w for w in res["waiting"])
    sb["characters"][1]["reference_choice"] = 2
    img.calls.clear()
    keyframes.run_refs(sb=sb, chain=[img], console=quiet())
    teen = [c for c in img.calls]
    assert len(teen) == 4 and all(len(refs) == 1 for _, _, refs in teen)  # the parent sheet only
    assert all("me_child" in refs[0] for _, _, refs in teen)
    assert "Keep the family resemblance" in teen[0][0]
    sb["characters"][0]["reference_choice"] = 1  # chosen sheets are locked: nothing regenerates
    img.calls.clear()
    keyframes.run_refs(sb=sb, chain=[img], console=quiet())
    assert img.calls == []


def test_keyframe_references_follow_the_rule(outputs):
    sb = storyboard()
    refs_chosen(sb, outputs)
    jobs = {j.item: j for j in keyframes.keyframe_jobs(sb) if j.index == 0}
    assert [w for w, _ in jobs["s01"].refs] == ["the style reference, which also shows the red toolbox"]
    assert [w for w, _ in jobs["s02"].refs] == ["the father", "the boy"]  # sheets carry the style
    assert len(jobs["s03"].refs) == 1  # nothing else carries the look


def test_budget_guard_defers_whole_items_by_priority(outputs, monkeypatch):
    sb = storyboard()
    refs_chosen(sb, outputs)
    monkeypatch.setattr(keyframes, "neurons_today", lambda log_path=None: keyframes.NEURONS_PER_DAY - 900.0)
    img = FakeImage()
    jobs = keyframes.keyframe_jobs(sb)
    res = keyframes.run_jobs(jobs, chain=[img], console=quiet())
    made = {c[1] for c in img.calls}
    assert res["generated"] == len(img.calls) and res["generated"] % 3 == 0  # whole shots only
    first = min(jobs, key=lambda j: j.priority).item
    assert {j.seed for j in jobs if j.item == first} <= made  # the most important shot first


def test_a_changed_reference_changes_the_key(outputs, tmp_path):
    a, b = tmp_path / "a.jpg", tmp_path / "b.jpg"
    a.write_bytes(b"one")
    b.write_bytes(b"one")
    img = FakeImage()
    job = keyframes.Job("keyframes", "s02", 0, 7, "text", [("the father", a)])
    k1 = keyframes.job_key(job, img)
    a.write_bytes(b"two")
    assert keyframes.job_key(job, img) != k1
    assert keyframes.job_key(keyframes.Job("keyframes", "s02", 0, 7, "text", [("the father", b)]), img) == k1


def test_contact_sheet_and_cache_hits(outputs):
    sb = storyboard()
    img = refs_chosen(sb, outputs)
    img.calls.clear()
    res = keyframes.run_keyframes(sb=sb, chain=[img], console=quiet(), only=["s02"])
    assert res["generated"] == 3 and len(res["sheets"]) == 1
    with Image.open(outputs.parent / res["sheets"][0]) as sheet:
        assert sheet.width > 3 * 400
    res = keyframes.run_keyframes(sb=sb, chain=[img], console=quiet(), only=["s02"])
    assert res["generated"] == 0 and res["hits"] == 3


def test_choose_edits_exactly_one_field(tmp_path):
    src = sbm.STORYBOARD.read_text(encoding="utf-8")
    path = tmp_path / "storyboard.json"
    path.write_text(src, encoding="utf-8")
    before = json.loads(src)
    target = next(s for s in before["shots"] if s.get("layers"))
    item = f"{target['id']}{target['layers'][1]['id']}"
    choose(item, 7, path)
    after = json.loads(path.read_text(encoding="utf-8"))
    target_after = next(s for s in after["shots"] if s["id"] == target["id"])
    assert target_after["layers"][1]["keyframe_choice"] == 7
    target_after["layers"][1]["keyframe_choice"] = target["layers"][1]["keyframe_choice"]
    assert after == before
    assert len(path.read_text(encoding="utf-8").splitlines()) == len(src.splitlines())  # no reformatting
    with pytest.raises(KeyError):
        choose("nobody", 1, path)


def test_rough_cut_frames_match_the_timeline():
    sb = minimal_storyboard()
    tl = sbm.timeline(sb)
    counts = assemble.frame_counts(tl)
    assert len(counts) == len(sb["shots"]) + 1
    assert sum(counts) == round(tl["total_s"] * assemble.FPS)
    segs = [{"kind": "split", "inputs": ["a.mp4", "b.mp4"], "focus": [None, None], "frames": 48},
            {"kind": "card", "inputs": ["end.png"], "focus": [], "frames": 72}]
    graph, n = assemble.segment_filters(segs, "9x16")
    assert n == 3 and "vstack=inputs=2" in graph and "scale=720:640" in graph and "trim=end_frame=72" in graph
    assert "hstack=inputs=2" in assemble.segment_filters(segs, "16x9")[0]


def test_choose_a_music_candidate(tmp_path):
    sb = minimal_storyboard()
    path = tmp_path / "storyboard.json"
    path.write_text(json.dumps(sb, indent=2), encoding="utf-8")
    assert choose("main", 2, path) == "main: main = 2"
    assert json.loads(path.read_text(encoding="utf-8"))["music"]["chosen"] == {"main": 2}
    choose("main", None, path)
    assert json.loads(path.read_text(encoding="utf-8"))["music"]["chosen"] == {"main": None}
