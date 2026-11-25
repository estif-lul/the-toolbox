"""The script stage without network: what it sends, what it writes, and what it never touches."""

import json

import pytest

from pipeline import script
from pipeline.common import storyboard as sbm
from pipeline.common.log import read_log
from pipeline.common.retry import FatalError
from pipeline.providers.base import TextResult

from test_schema import minimal_storyboard

DESIGN_MD = """# DESIGN

## 2. Ideation
not sent

## 3. Story

This paragraph is about the pipeline, not the story.

### Logline
A son remembers.

### Treatment
Morning light on a red toolbox.

### Shot reasons
| s01 | the human answer |

## 4. User test 1
not sent either
"""


class FakeText:
    name = "fake_text"

    def __init__(self, model="fake-1", data=None, fail=None):
        self.model, self.params, self.min_interval_s = model, {"temperature": 0.8}, 0
        self.data = data if data is not None else minimal_storyboard()
        self.fail = fail
        self.calls: list[tuple[str, dict | None]] = []

    def generate_json(self, prompt, schema=None):
        self.calls.append((prompt, schema))
        if self.fail is not None and (schema is not None or self.fail.status != 400):
            raise self.fail
        return TextResult(self.data, json.dumps(self.data), {"usage": {"prompt_tokens": 10, "output_tokens": 20}})


@pytest.fixture
def stage(tmp_path, run_log, monkeypatch):
    design = tmp_path / "DESIGN.md"
    design.write_text(DESIGN_MD, encoding="utf-8")
    monkeypatch.setattr(script, "artifact_path",
                        lambda stage, item, key, ext: tmp_path / "outputs" / stage / item / f"{key[:16]}.{ext}")
    return {"design": design, "out": tmp_path / "storyboard.draft.json", "root": tmp_path / "outputs"}


def _run(stage, provider, **kw):
    return script.run_script(chain=[provider], design_path=stage["design"], out=stage["out"],
                             manifest_root=stage["root"], **kw)


def test_extract_section_sends_only_the_story_and_not_the_shot_reasons():
    brief = script.extract_section(DESIGN_MD)
    assert brief.startswith("### Logline") and "Morning light" in brief
    assert "human answer" not in brief and "not sent" not in brief and "pipeline" not in brief


def test_extract_section_fails_clearly_when_missing():
    with pytest.raises(ValueError, match="3. Story"):
        script.extract_section("# nothing here\n")


def test_real_design_md_has_a_story_section():
    brief = script.extract_section(script.DESIGN.read_text(encoding="utf-8"))
    for heading in ("### Logline", "### Treatment", "### Beats", "### Characters",
                    "### Visual approach", "### Sound approach"):
        assert heading in brief
    assert "### Shot reasons" not in brief


def test_gemini_schema_drops_unsupported_keywords_and_keeps_structure():
    schema = json.loads(sbm.SCHEMA.read_text(encoding="utf-8"))
    g = script.gemini_schema(schema)
    text = json.dumps(g)
    for kw in ('"pattern"', '"const"', '"if"', '"then"', '"exclusiveMinimum"', '"propertyNames"', '"$schema"',
               '"minimum"', '"maximum"', '"minItems"', '"maxItems"', '"minLength"'):
        assert kw not in text, kw
    assert "description" not in g and "description" not in g["$defs"]["shot"]["properties"]["reason"]
    assert "description" in g["$defs"]["shot"]["properties"] or "description" in g["properties"]["characters"]["items"]["properties"]
    assert g["properties"]["schema_version"]["enum"] == [1]
    assert len(g["$defs"]["narration_line"]["anyOf"]) == 2
    assert g["$defs"]["shot"]["additionalProperties"] is False
    move = schema["$defs"]["kenburns"]["properties"]["move"]["enum"]
    assert g["$defs"]["kenburns"]["properties"]["move"]["enum"] == move
    assert "echo_line" in g["$defs"] and g["required"] == schema["required"]


def test_generates_a_draft_logs_it_and_never_touches_storyboard_json(stage, run_log):
    before = sbm.STORYBOARD.read_bytes() if sbm.STORYBOARD.exists() else None
    fake = FakeText()
    res = _run(stage, fake)
    assert res["status"] == "generated" and res["shots"] == 8 and res["schema_errors"] == 0
    assert json.loads(stage["out"].read_text(encoding="utf-8")) == fake.data
    prompt, constraint = fake.calls[0]
    assert "Morning light" in prompt and "JSON Schema" in prompt and constraint is not None
    calls = [r for r in read_log(run_log) if r["event"] == "model_call"]
    assert len(calls) == 1 and calls[0]["stage"] == "script" and calls[0]["status"] == "ok"
    assert calls[0]["output"] and calls[0]["cache_key"]
    after = sbm.STORYBOARD.read_bytes() if sbm.STORYBOARD.exists() else None
    assert before == after


def test_second_run_is_a_cache_hit_and_force_regenerates(stage, run_log):
    fake = FakeText()
    _run(stage, fake)
    res = _run(stage, fake)
    assert res["status"] == "cache_hit" and len(fake.calls) == 1
    assert [r["event"] for r in read_log(run_log)][-1] == "cache_hit"
    res = _run(stage, fake, force=True)
    assert res["status"] == "generated" and len(fake.calls) == 2


def test_a_draft_from_the_fallback_still_counts_as_a_cache_hit(stage, run_log):
    primary, fallback = FakeText("primary"), FakeText("fallback")
    script.run_script(chain=[fallback], design_path=stage["design"], out=stage["out"], manifest_root=stage["root"])
    res = script.run_script(chain=[primary, fallback], design_path=stage["design"], out=stage["out"],
                            manifest_root=stage["root"])
    assert res["status"] == "cache_hit" and res["model"] == "fallback" and primary.calls == []


def test_refuses_to_write_storyboard_json(stage):
    with pytest.raises(ValueError, match="never writes storyboard.json"):
        script.run_script(chain=[FakeText()], design_path=stage["design"], out=sbm.STORYBOARD)


def test_schema_rejected_by_the_api_retries_without_the_constraint(stage, run_log):
    fake = FakeText(fail=FatalError("400 INVALID_ARGUMENT: response_json_schema is too complex", status=400))
    res = _run(stage, fake)
    assert res["status"] == "generated"
    assert fake.calls[0][1] is not None and fake.calls[1][1] is None


def test_broken_draft_is_kept_and_its_errors_reported(stage):
    bad = minimal_storyboard()
    bad["shots"][0]["id"] = "shot1"
    res = _run(stage, FakeText(data=bad))
    assert res["status"] == "generated" and res["schema_errors"] + res["semantic_errors"] > 0
    assert stage["out"].exists()


def test_dry_run_makes_no_call(stage, capsys):
    fake = FakeText()
    res = _run(stage, fake, dry_run=True)
    assert res["status"] == "dry_run" and fake.calls == []
    assert "Rules:" in capsys.readouterr().out
