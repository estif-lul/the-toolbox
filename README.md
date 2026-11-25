# The Toolbox

A 60–90 second Heritage Short about my dad, who fixes everything himself. It's told through the
tools in his red toolbox and his line *"እስኪ እንየው"* ("Let's look at it first"). The film is
made by a small code pipeline: `storyboard.json` is the contract, and each stage (keyframes,
moving shots, music, narration, assembly) reads it and writes its outputs. Only what changed
gets regenerated.

> **Status: Step 0 (scaffold + smoke test).** The stages are added one at a time.
> This README is completed in Step 6.

## Quickstart

Prerequisites: [uv](https://docs.astral.sh/uv/), FFmpeg (on PATH), GNU Make (optional: every
target is also `uv run python -m pipeline.run <command>`).

```sh
cp .env.example .env      # add the keys (only needed for stages that must regenerate)
make setup                # Python 3.12 + locked deps, secrets pre-commit hook
make smoke                # one call per provider, latency logged to runs.jsonl
make check                # secrets scan + tests + storyboard validation
make help                 # every target
```

`make film` (Step 5) runs the whole pipeline end to end.

## Where things are
- `DESIGN.md`: audience, intent, user tests ·
  `ETHICS.md`: consent, privacy, labelling, licences
- `pipeline/`: stages; `pipeline/common/`: logging, caching, retries, storyboard, FFmpeg;
  `pipeline/providers/`: one adapter per model API, chosen by `config/providers.yaml`
- `runs.jsonl`: one line per model call · `FAILURES.md`, `EXPERIMENTS.md`, `COSTS.md`

Made with AI. The characters are fictional cartoons; no real person's likeness or voice is used.
