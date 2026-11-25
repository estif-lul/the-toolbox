"""The storyboard contract: the schema is valid, the real storyboard passes, and deliberately broken
storyboards fail with a message that says what is wrong."""

import copy
import json

import pytest
from jsonschema import Draft202012Validator

from pipeline.common import storyboard as sbm


def _shot(i: int) -> dict:
    return {
        "id": f"s{i:02d}", "beat": "beat", "reason": f"reason for shot {i}",
        "shot_size": "medium", "camera": "static", "characters": ["dad"], "props": [],
        "image_prompt": "the father in the yard", "seed": 2000 + i, "keyframe_choice": None,
        "motion": "wan", "motion_prompt": "he nods slowly, camera static",
        "kenburns": {"move": "push_in" if i % 2 else "pull_out", "amount": 0.08},
        "crop_focus": {"x": 0.5, "y": 0.5},
        "narration": [{"voice": "narrator", "text": "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen"}],
        "layers": None, "min_duration_s": 4.0, "pad_before_s": 0.4, "pad_after_s": 0.6,
        "duration_override_s": None, "transition_in": "cut", "priority": i,
    }


def minimal_storyboard(n_shots: int = 8) -> dict:
    return {
        "schema_version": 1, "title": "T", "logline": "L",
        "format": {"fps": 24, "master_aspect": "1:1", "master_px": 1024,
                   "exports": [{"name": "9x16", "w": 720, "h": 1280}],
                   "target_duration_s": {"min": 60, "max": 90}},
        "style": {"block": "cartoon", "negative": "text", "composition": "centred", "reference_choice": None},
        "characters": [{"id": "dad", "description": "the father", "seed": 1}],
        "props": [{"id": "toolbox", "description": "the red toolbox"}],
        "voices": {"narrator": {"voice": "Achird", "style": "warm"}, "dad": {"voice": "Algenib", "style": "calm"}},
        "music": {"cues": [{"id": "main", "from_shot": "s01", "to_shot": f"s{n_shots:02d}", "intent": "i",
                            "caption": "c", "instrumental": True, "seeds": [1]}],
                  "chosen": {"main": None},
                  "duck": {"threshold": 0.02, "ratio": 6, "attack_ms": 300, "release_ms": 1500}},
        "shots": [_shot(i) for i in range(1, n_shots + 1)],
        "end_card": {"duration_s": 3.0, "lines": ["Made with AI"]},
    }


def errors(sb: dict) -> list[str]:
    return sbm.validate(sb).errors


def test_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(json.loads(sbm.SCHEMA.read_text(encoding="utf-8")))


def test_minimal_storyboard_is_valid():
    rep = sbm.validate(minimal_storyboard())
    assert rep.errors == []


def test_real_storyboard_validates():
    if not sbm.STORYBOARD.exists():
        pytest.skip("storyboard.json not written yet")
    sb = sbm.load_storyboard()
    rep = sbm.validate(sb)
    assert rep.errors == [], rep.errors
    assert all(str(s["reason"]).strip() for s in sb["shots"])


# --- the five deliberately broken storyboards -------------------------------------------------

def _duplicate_id(sb):
    sb["shots"][3]["id"] = "s03"


def _unknown_character(sb):
    sb["shots"][2]["characters"] = ["dad", "uncle"]


def _missing_reason(sb):
    del sb["shots"][4]["reason"]


def _bad_enum(sb):
    sb["shots"][1]["kenburns"]["move"] = "spin"


def _too_few_shots(sb):
    sb["shots"] = sb["shots"][:5]
    sb["music"]["cues"][0]["to_shot"] = "s05"


@pytest.mark.parametrize("break_it, expected", [
    (_duplicate_id, "duplicate shot id s03"),
    (_unknown_character, "s03: unknown character 'uncle'"),
    (_missing_reason, "'reason' is a required property"),
    (_bad_enum, "'spin' is not one of"),
    (_too_few_shots, "need 8-12 shots, found 5"),
], ids=["duplicate-id", "unknown-character", "missing-reason", "bad-enum", "too-few-shots"])
def test_broken_storyboards_fail(break_it, expected):
    sb = minimal_storyboard()
    break_it(sb)
    errs = errors(sb)
    assert any(expected in e for e in errs), errs


# --- further semantic checks ------------------------------------------------------------------

def test_blank_reason_fails_both_layers():
    sb = minimal_storyboard()
    sb["shots"][0]["reason"] = "   "
    errs = errors(sb)
    assert any("s01: missing 'reason'" in e for e in errs)
    assert any(e.startswith("schema: shots/0/reason") for e in errs)


def test_typo_in_field_name_is_caught():
    sb = minimal_storyboard()
    sb["shots"][0]["image_promt"] = sb["shots"][0].pop("image_prompt")
    errs = errors(sb)
    assert any("Additional properties are not allowed ('image_promt'" in e for e in errs), errs


def test_unknown_prop_and_bad_derived_from():
    sb = minimal_storyboard()
    sb["shots"][0]["props"] = ["ladder"]
    sb["characters"].append({"id": "dad_now", "description": "older", "seed": 2, "derived_from": "mum"})
    errs = errors(sb)
    assert any("s01: unknown prop 'ladder'" in e for e in errs)
    assert any("derived_from 'mum'" in e for e in errs)


def test_amharic_line_needs_english_subtitle():
    sb = minimal_storyboard()
    sb["shots"][0]["narration"].append({"voice": "dad", "lang": "am", "text": "እስኪ እንየው"})
    assert any("has no English 'subtitle'" in e for e in errors(sb))
    sb["shots"][0]["narration"][-1]["subtitle"] = "Let's look at it first."
    assert errors(sb) == []


def test_echo_must_point_at_a_spoken_line():
    sb = minimal_storyboard()
    sb["shots"][4]["narration"].append({"echo_of": "s01:0", "gain_db": -8, "reverb": True})
    assert errors(sb) == []
    sb["shots"][5]["narration"].append({"echo_of": "s05:1"})  # an echo of an echo
    assert any("which is itself an echo" in e for e in errors(sb))
    sb["shots"][5]["narration"][-1]["echo_of"] = "s09:0"
    assert any("does not point at an existing line" in e for e in errors(sb))


def test_echo_line_rejects_speech_fields():
    sb = minimal_storyboard()
    sb["shots"][0]["narration"].append({"echo_of": "s02:0", "voice": "dad"})
    assert any("schema: shots/0/narration/1" in e for e in errors(sb))


def test_music_must_cover_every_shot():
    sb = minimal_storyboard()
    sb["music"]["cues"][0]["to_shot"] = "s06"
    assert any("music cues do not cover shots: s07, s08" in e for e in errors(sb))


def test_wan_shot_needs_motion_prompt():
    sb = minimal_storyboard()
    sb["shots"][0]["motion_prompt"] = None
    assert any("s01: motion is 'wan' but motion_prompt is empty" in e for e in errors(sb))


def test_privacy_lint_warns_on_phone_number():
    sb = minimal_storyboard()
    sb["shots"][0]["image_prompt"] = "a note with +251 911 234 567 on it"
    rep = sbm.validate(sb)
    assert rep.ok and any("phone number" in w for w in rep.warnings)


def test_estimated_timeline_adds_up():
    sb = minimal_storyboard()
    tl = sbm.timeline(sb)
    assert tl["estimated"] is True
    total = sum(s["duration_s"] for s in tl["shots"]) + tl["end_card"]["duration_s"]
    assert tl["total_s"] == pytest.approx(total, abs=0.01)
    starts = [s["start_s"] for s in tl["shots"]]
    assert starts == sorted(starts) and starts[0] == 0


def test_measured_timing_enforces_60_to_90_seconds():
    sb = minimal_storyboard()
    long_timing = {s["id"]: [{"line_idx": 0, "duration_s": 12.0}] for s in sb["shots"]}
    errs = sbm.validate(sb, timing=long_timing).errors
    assert any("must be 60-90s" in e and "Trim" in e for e in errs), errs


def test_real_storyboard_is_inside_the_target_when_estimated():
    if not sbm.STORYBOARD.exists():
        pytest.skip("storyboard.json not written yet")
    tl = sbm.timeline(copy.deepcopy(sbm.load_storyboard()))
    assert 60 <= tl["total_s"] <= 90
