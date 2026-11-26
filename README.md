# The Toolbox

A 60–90 second Heritage Short about my dad, who fixes everything himself. It's told through the
tools in his red toolbox and his line *"እስኪ እንየው"* ("Let's look at it first"). The film is
made by a small code pipeline: `storyboard.json` is the contract, and each stage (keyframes,
moving shots, music, narration, assembly) reads it and writes its outputs. Only what changed
gets regenerated.

> **Status: Steps 4-5 (moving shots, music, the final edit).** Every shot has a chosen keyframe;
> the final edit runs end to end in both formats (`outputs/final/the_toolbox_{9x16,16x9}.mp4`,
> QC in `outputs/final/qc.json`) with Ken Burns stills wherever no Wan clip exists yet. Wan 2.2
> moving shots and ACE-Step score candidates run on Kaggle GPUs and are pulled into the cache as
> they finish. This README is completed in Step 6.

## Quickstart

Prerequisites: [uv](https://docs.astral.sh/uv/), FFmpeg (on PATH), GNU Make (optional: every
target is also `uv run python -m pipeline.run <command>`).

```sh
cp .env.example .env      # add the keys (only needed for stages that must regenerate)
make setup                # Python 3.12 + locked deps, secrets pre-commit hook
make smoke                # one call per provider, latency logged to runs.jsonl
make check                # secrets scan + tests + storyboard validation
make validate             # just the storyboard: JSON Schema + semantic checks + estimated length
make script               # an AI draft of the storyboard -> storyboard.draft.json (never storyboard.json)
make audition ROLE=dad    # the role's candidate stock voices, one TTS request per voice
make narration            # every narration line -> WAV (cached per line) + outputs/narration/timing.json
make narration-check      # hear each line back (transcribe), repair a batch cut in the wrong pause
make radio                # radio cut: narration + placeholder pad + subtitles on black -> outputs/cuts/
make refs                 # style + character reference candidates (whatever is ready) + contact sheets
make choose ITEM=dad PICK=4   # record a pick in storyboard.json (style, a character, s05, s10a ...)
make revise ITEM=dad FROM=0 EDIT="remove the pencil"   # edit a chosen sheet (new candidates)
make keyframes            # 3 candidates per shot, references attached, crop previews drawn
make rough                # Ken Burns clips + the radio-cut sound -> outputs/cuts/rough_kb_{9x16,16x9}.mp4
make shots-pilot          # Kaggle: the 2 highest-priority Wan jobs (measures minutes per clip)
make shots-push           # Kaggle: every stale Wan job (a private dataset + a GPU kernel)
make shots-pull           # pull finished clips into outputs/shots/ (one model_call each, with GPU seconds)
make music-push           # Kaggle: 3 ACE-Step score candidates
make music-pull           # pull them, then render the radio cut once per candidate (outputs/cuts/audition_cN.mp4)
make choose ITEM=main PICK=2  # record the score you chose
make assemble             # the final edit, both formats, QC -> outputs/final/
make film                 # everything above in order, all cached (add FLAGS=--gpu to push stale Kaggle jobs)
make help                 # every target
```

Narration and the free tier: Gemini TTS allows 10 requests a day per model, so lines that miss the
cache are sent several to a request and cut apart at the pauses; the whole film is 3 requests.
Editing one line costs one request for that line. `make narration DRY_RUN=1` shows what a run would
send and how much of today's quota runs.jsonl says is left.

Kaggle needs `KAGGLE_API_TOKEN` (and phone verification for GPU + internet). Without it, `make film`
uses the clips and music already in `outputs/` and only reassembles.

## Where things are
- `storyboard.json`: the contract every stage reads (shots, prompts, narration, voices, music) ·
  `schema/storyboard.schema.json`: its JSON Schema
- `DESIGN.md`: audience, intent, story, visual and sound approach, shot reasons, user tests ·
  `ETHICS.md`: consent, privacy, labelling, licences
- `pipeline/`: stages; `pipeline/common/`: logging, caching, retries, storyboard, FFmpeg;
  `pipeline/providers/`: one adapter per model API, chosen by `config/providers.yaml`
- `runs.jsonl`: one line per model call · `FAILURES.md`, `EXPERIMENTS.md`, `COSTS.md`

Made with AI. The characters are fictional cartoons; no real person's likeness or voice is used.
