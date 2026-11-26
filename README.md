# The Toolbox

A 75-second animated Heritage Short about my dad, who fixes everything himself. It is told through
the tools in his red toolbox and his line *"እስኪ እንየው"* ("Let's look at it first"), and it ends
with me, grown up, calling him to say I fixed something myself.

**The films:** `outputs/final/the_toolbox_9x16.mp4` (phones) and `outputs/final/the_toolbox_16x9.mp4`
(YouTube, laptops). QC results are in `outputs/final/qc.json`.

It is made by a small code pipeline. `storyboard.json` is the contract: each stage (narration,
reference sheets, keyframes, moving shots, music, the edit) reads it and writes cached outputs, so
**changing one shot regenerates only that shot**. Every model call is logged to `runs.jsonl`.

> **Status (2026-11-26):** the final edit runs end to end in both formats with the chosen score.
> Wan 2.2 moving shots are pulled in as the Kaggle batch finishes; any shot without a clip uses
> its Ken Burns move. User test 2 is out.

## Quickstart

Prerequisites: [uv](https://docs.astral.sh/uv/), FFmpeg 6+ on PATH, GNU Make. Make is optional:
every target is also `uv run python -m pipeline.run <command>`.

```sh
git clone https://github.com/estif-lul/the-toolbox && cd the-toolbox
make setup                # Python 3.12 + locked deps, secrets pre-commit hook
make film                 # validate -> narration -> keyframes -> ken burns -> Kaggle pull -> final edit
```

**No keys are needed to rebuild the film.** `outputs/` is committed, so `make film` in a clean
clone gets a cache hit at every stage and only reassembles. This was tested on 2026-11-26 in a
fresh clone with no keys: both films built and QC passed. Keys are needed only for stages that must
regenerate, and a missing key stops the run with the stage, the key and where to get it
(`cp .env.example .env`).

## Change one shot

Edit one thing in `storyboard.json` and run `make film`. Only what depends on it is regenerated, and
`runs.jsonl` shows it. Example: after four keyframe choices this morning (s03, s04, s07, s08), the Ken
Burns stage re-rendered exactly those four and reused the rest (run `20261126-100601-5954`, abridged):

```json
{"event": "cache_hit",  "stage": "kenburns", "shot_id": "s01", "cache_key": "b39898205b368a36…"}
{"event": "cache_hit",  "stage": "kenburns", "shot_id": "s02", "cache_key": "c147b9394a26aa6d…"}
{"event": "model_call", "stage": "kenburns", "shot_id": "s03", "cache_key": "e4d11f94bb157fbf…", "latency_s": 2.9}
{"event": "model_call", "stage": "kenburns", "shot_id": "s04", "cache_key": "79b97e9f9a2bc3e7…"}
{"event": "cache_hit",  "stage": "kenburns", "shot_id": "s05", "cache_key": "a6fc56bb48529e03…"}
…
```

Editing a narration line costs one TTS request for that line. Its new length changes that shot's
Ken Burns clip, and the edit is reassembled. Why: ARCHITECTURE.md §3 (cache keys, with a worked example).

## All targets

```sh
make check                # secrets scan + tests + storyboard validation
make validate             # the storyboard: JSON Schema + semantic checks + estimated length
make smoke                # one call per provider, latency logged
make script               # an AI draft of the storyboard -> storyboard.draft.json (never storyboard.json)
make audition ROLE=dad    # a role's candidate stock voices
make narration            # every narration line -> WAV (cached per line) + outputs/narration/timing.json
make narration-check      # hear each line back (transcribe); repair a batch cut in the wrong pause
make radio                # radio cut: narration + placeholder pad + subtitles on black
make refs                 # style + character reference sheets + contact sheets
make keyframes            # 3 candidates per shot, references attached, 9:16 / 16:9 crop previews drawn
make choose ITEM=s05 PICK=0   # record a pick: style, a character, a shot, a layer (s10a), the score (main)
make revise ITEM=dad FROM=0 EDIT="remove the pencil"   # edit a chosen sheet (new candidates)
make kenburns             # a slow push / pull / pan per shot (the fallback for every shot)
make rough                # Ken Burns stills + the radio-cut sound, both formats
make shots-pilot          # Kaggle: the 2 highest-priority Wan jobs (measures minutes per clip)
make shots-push           # Kaggle: every stale Wan job (a private dataset + a GPU kernel)
make shots-pull           # pull finished clips into the cache (one model_call each, with GPU seconds)
make music-push / music-pull   # Kaggle: 3 ACE-Step score candidates; pull renders one audition each
make assemble             # the final edit, both formats, QC -> outputs/final/
make film                 # everything in order, cached (FLAGS=--gpu also pushes stale Kaggle jobs)
make costs                # COSTS.md tables from runs.jsonl
make help                 # every target
```

**The free tiers shaped the design:**
- **Gemini TTS** allows 10 requests a day per model. Lines are sent several to a request and cut
  apart at the pauses, and every cut is checked by hearing it back. The whole film is 3 requests.
- **Workers AI** allows 10,000 neurons a day. The keyframe stage generates in shot-priority order
  and defers whole shots past the allowance.
- **Kaggle GPU stage:** set `KAGGLE_API_TOKEN` (and verify your phone for GPU + internet). The
  kernels run on T4 x2, and the job hash guards against stale inputs.

## Cost

Everything ran on free tiers, so I paid $0. At list price the same calls would cost about **$0.17**,
plus the Kaggle GPU time. The tables are generated from `runs.jsonl` (`make costs`): see COSTS.md.

## Where things are

- `storyboard.json` (the contract) · `schema/storyboard.schema.json` (its JSON Schema)
- `pipeline/`: one module per stage; `pipeline/common/`: logging, cache, retries, storyboard, FFmpeg,
  crops, subtitles; `pipeline/providers/`: one adapter per model API, chosen by
  `config/providers.yaml`; `pipeline/kaggle/`: the GPU kernels
- `outputs/<stage>/manifest.json`: the current artifact per item; old candidates stay beside it
- `runs.jsonl`: one line per call, cache hit, retry, fallback and Kaggle job
- **Docs:**
  - DESIGN.md: audience, story, shot reasons, user tests
  - ARCHITECTURE.md: stages, contract, cache keys, failure handling
  - EXPERIMENTS.md, FAILURES.md, COSTS.md
  - ETHICS.md: consent, privacy, labelling, licences
  - docs/PAID_LANE.md

## Licences and labelling

The models, tools and font used, with their licences, are listed in ETHICS.md §6:
- **Models:** FLUX.2 klein 4B and Wan 2.2 TI2V-5B (both Apache 2.0); ACE-Step 1.5 (MIT); Gemini (API terms).
- **Tools:** FFmpeg.
- **Font:** Atkinson Hyperlegible (OFL).

**Made with AI.** The characters are fictional cartoons inspired by my father and me. No photo,
likeness or voice of a real person was used, and the voices are stock TTS voices. The film ends with
a "Made with AI" card and carries an MP4 comment saying so.
