"""The script stage (`make script`): an AI draft of the whole storyboard, to compare with the
hand-written storyboard.json (EXPERIMENTS.md E01).

- Input: the "## 3. Story" section of DESIGN.md (logline, treatment, beats, characters, visual and
  sound approach; the "Shot reasons" table is left out because it is the human answer), the
  storyboard JSON Schema, and the rules below.
- Output: storyboard.draft.json, a versioned copy at outputs/script/draft/<key16>.json, and next
  to it the exact prompt sent (.prompt.txt) and the draft's validation report (.report.json). **It never writes storyboard.json**: a person reads the draft and
  merges the good parts by hand, so the contract only changes in a reviewed commit.
- Cached like every stage: the same brief, schema, rules and model give the same key, and a cache
  hit makes no call. `--force` asks for a new draft; `--dry-run` prints the prompt only.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .common import storyboard as sbm
from .common.cache import (Manifest, artifact_path, atomic_write_json, atomic_write_text, cache_key,
                           canonical_json, rel, sha256_text)
from .common.env import ROOT
from .common.invoke import AllProvidersFailed, invoke
from .common.log import log_event
from .providers import registry

STAGE = "script"
STAGE_VERSION = 1
ITEM = "draft"
DESIGN = ROOT / "DESIGN.md"
DRAFT = ROOT / "storyboard.draft.json"
SECTION = "3. Story"
LEFT_OUT = ("Shot reasons",)

RULES = """\
You are the storyboard writer for "The Toolbox", a 60-90 second animated short (a "Heritage
Short") about a Habesha (Ethiopian) father who fixes everything at home himself, told by his son.
It is watched on phones by family and friends, often with the sound off.

Write the complete storyboard as ONE JSON object that validates against the JSON Schema below.
The brief (from the design document) follows the rules.

Rules:
1. 10 shots, ids s01..s10 in story order. Every shot has a "reason": why it exists in the story.
2. English narration, short lines written for the ear, 120-160 words in total (about 2.3 words per
   second), voice "narrator". Leave room for silence.
3. Dad speaks only Amharic, exactly these three lines, with voice "dad", "lang": "am" and the
   English "subtitle": "እስኪ እንየው" = "Let's look at it first." (the power cut, then echoed when
   the grown son opens the toolbox, using an echo line {"echo_of": "<shot>:<line index>"});
   "ቀስ በቀስ እንቁላል በእግሩ ይሄዳል" = "Slowly, slowly, the egg walks on its own legs." (the turn);
   "ጎበዝ ልጄ" = "Well done, my son." (the ending phone call).
4. "image_prompt" is the subject + setting + shot size only. Do NOT describe what the characters
   or recurring objects look like and do NOT describe the art style: code appends the character
   descriptions, the prop descriptions, style.composition and style.block to every prompt.
   Refer to characters as "the father", "the boy", "the teenage son", "the grown son".
5. "motion_prompt" is one gentle movement + the camera only (e.g. "the candle flame flickers,
   camera static"). Never re-describe the subject.
6. Every shot has a Ken Burns fallback move; never the same move in two consecutive shots.
7. Characters are fictional cartoons. No real names other than "Dad"; no brands, number plates,
   addresses or workplaces. Describe the style by its qualities, never by naming an artist or a
   studio.
8. Square 1:1 masters of 1024 px with the subject centred; exports "9x16" (720x1280) and "16x9"
   (1280x720); 24 fps; target_duration_s 60-90.
9. All "*_choice" fields are null. "layers" is null unless a shot is a split screen (then exactly
   two layers "a" and "b"). The end card must include the line "Made with AI".
10. Character ids: dad (the memories), dad_now (about fifty, only at the end), me_child, me_teen,
    me_adult. Give each a fixed description of 25-40 words with a colour anchor.
"""

# The output constraint sent to Gemini keeps only the structure: types, required fields, closed
# objects, enums and references. The full schema rides in the prompt text, and the draft is
# validated against all of it afterwards. Numeric bounds, array lengths and descriptions are left
# out: with them Gemini refused the schema ("too many states for serving", FAILURES.md F08).
GEMINI_KEYWORDS = {
    "type", "properties", "required", "additionalProperties", "enum", "items", "anyOf", "$ref", "$defs",
}


def extract_section(md: str, title: str = SECTION, left_out: tuple[str, ...] = LEFT_OUT) -> str:
    """The `## <title>` section's `###` subsections, minus the ones in `left_out`."""
    out: list[str] = []
    inside = keep = False
    for line in md.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip() == title
            continue
        if not inside:
            continue
        if line.startswith("### "):
            keep = line[4:].strip() not in left_out
        if keep:
            out.append(line)
    text = "\n".join(out).strip()
    if not text:
        raise ValueError(f"DESIGN.md has no '## {title}' section with '###' subsections")
    return text


def gemini_schema(node: Any) -> Any:
    """The structural core of the schema, in the subset Gemini serves: other keywords dropped,
    `const` as a one-value enum, the narration if/then/else as anyOf."""
    if isinstance(node, list):
        return [gemini_schema(n) for n in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in ("properties", "$defs"):
            # the storyboard's optional "$schema" (an editor hint) is not something to generate
            out[key] = {k: gemini_schema(v) for k, v in value.items() if k != "$schema"}
        elif key == "const":
            out["enum"] = [value]
        elif key == "if" and "then" in node and "else" in node:
            out["anyOf"] = [gemini_schema(node["then"]), gemini_schema(node["else"])]
        elif key in GEMINI_KEYWORDS:
            out[key] = gemini_schema(value)
    if "enum" in out and "type" not in out and all(isinstance(v, str) for v in out["enum"]):
        out["type"] = "string"
    return out


def build_prompt(brief: str, schema: dict) -> str:
    return (f"{RULES}\nJSON Schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
            f"Brief (from the design document):\n\n{brief}\n")


def summarize(sb: dict) -> dict:
    """The numbers E01 compares: shots, words, estimated length, validation errors."""
    rep = sbm.validate(sb)
    shots = sb.get("shots") or []
    words = sum(len(str(line.get("text", "")).split()) for s in shots for line in s.get("narration") or []
                if "echo_of" not in line)
    try:
        est = sbm.timeline(sb)["total_s"]
    except Exception:  # noqa: BLE001 - a broken draft may not even have a timeline
        est = None
    return {"shots": len(shots), "narration_words": words, "estimated_total_s": est,
            "schema_errors": sum(e.startswith("schema:") for e in rep.errors),
            "semantic_errors": sum(not e.startswith("schema:") for e in rep.errors),
            "warnings": len(rep.warnings), "errors": rep.errors, "warning_text": rep.warnings}


def run_script(profile: str | None = None, *, force: bool = False, dry_run: bool = False,
               chain: Any = None, design_path: Path = DESIGN, out: Path = DRAFT,
               manifest_root: Path | None = None) -> dict:
    if Path(out).resolve() == sbm.STORYBOARD.resolve():
        raise ValueError("the script stage never writes storyboard.json; it writes storyboard.draft.json")
    brief = extract_section(Path(design_path).read_text(encoding="utf-8"))
    schema = json.loads(sbm.SCHEMA.read_text(encoding="utf-8"))
    constraint = gemini_schema(schema)
    prompt = build_prompt(brief, schema)
    if dry_run:
        print(prompt)
        return {"status": "dry_run", "prompt_chars": len(prompt)}

    chain = chain if chain is not None else registry.get_provider(STAGE, profile)
    providers = list(getattr(chain, "providers", chain))
    inputs = {"prompt_sha": sha256_text(prompt), "constraint_sha": sha256_text(canonical_json(constraint))}

    def key_for(p) -> str:
        return cache_key(stage=STAGE, stage_version=STAGE_VERSION, provider=p.name, model=p.model,
                         params={"temperature": p.params.get("temperature")}, inputs=inputs)

    manifest = Manifest(STAGE, manifest_root)
    if not force:
        for p in providers:  # a draft from any provider in the chain is a hit for the same inputs
            key = key_for(p)
            if manifest.is_fresh(ITEM, key):
                entry = manifest.get(ITEM)
                log_event("cache_hit", stage=STAGE, shot_id=ITEM, provider=p.name, model=p.model,
                          cache_key=key, output=entry["path"])
                path = ROOT / entry["path"]
                shutil.copyfile(path, out)
                return {"status": "cache_hit", "path": rel(path), "provider": p.name, "model": p.model,
                        **summarize(json.loads(path.read_text(encoding="utf-8")))}

    def save(p, key, result) -> Path:
        path = artifact_path(STAGE, ITEM, key, "json")
        atomic_write_json(path, result.data)
        atomic_write_text(path.with_suffix(".prompt.txt"), prompt)  # exactly what was sent
        return path

    try:
        r = invoke(providers, lambda p: p.generate_json(prompt, constraint), stage=STAGE, shot_id=ITEM,
                   input_hash=inputs["prompt_sha"], key_fn=key_for, save=save)
    except AllProvidersFailed as exc:
        # Gemini rejects schemas it cannot compile with a 400. Retry once without the output
        # constraint: the full schema is still in the prompt and the draft is validated anyway.
        if not any(getattr(err, "status", None) == 400 and "schema" in str(err).lower() for _, err in exc.errors):
            raise
        inputs["constraint_sha"] = None  # a different request, so a different cache key
        r = invoke(providers, lambda p: p.generate_json(prompt, None), stage=STAGE, shot_id=ITEM,
                   params={"constraint": "none (schema in prompt only)"}, input_hash=inputs["prompt_sha"],
                   key_fn=key_for, save=save)

    path = r.output
    report = summarize(r.value.data)
    atomic_write_json(path.with_suffix(".report.json"), report)
    manifest.put(ITEM, cache_key=r.cache_key, path=path, provider=r.provider.name, model=r.provider.model,
                 fell_back=r.fell_back, usage=(r.value.meta or {}).get("usage"))
    shutil.copyfile(path, out)
    return {"status": "generated", "path": rel(path), "provider": r.provider.name, "model": r.provider.model,
            "fell_back": r.fell_back, **report}


def main(profile: str | None, force: bool, dry_run: bool) -> int:
    from rich.console import Console

    console = Console()
    res = run_script(profile, force=force, dry_run=dry_run)
    if res["status"] == "dry_run":
        return 0
    console.print(f"script: {res['status']} via {res['provider']}:{res['model']} -> {res['path']} "
                  f"(copied to {DRAFT.name}; storyboard.json untouched)")
    console.print(f"draft: {res['shots']} shots, {res['narration_words']} narration words, "
                  f"~{res['estimated_total_s']} s estimated; {res['schema_errors']} schema error(s), "
                  f"{res['semantic_errors']} semantic error(s), {res['warnings']} warning(s)")
    for e in res["errors"][:15]:
        console.print(f"  [red]error[/red] {e}")
    if len(res["errors"]) > 15:
        console.print(f"  … {len(res['errors']) - 15} more in the .report.json")
    return 0
