# The paid lane (designed in, not yet used)

The film is made entirely on free tiers. This page describes how a paid provider plugs in, what
paying would buy at each stage, and the rules for adopting one.

## How it plugs in

- Every stage asks `registry.get_provider(stage, profile)` for a chain of adapters. You switch the
  lane with `make film PROFILE=paid` (or `--profile paid`). **`storyboard.json` does not change.**
- Provider and model are part of every cache key (ARCHITECTURE.md §3), so switching regenerates
  only the stages whose provider changed. The free and paid versions then sit side by side in
  `outputs/` for comparison.
- The paid adapters live in `pipeline/providers/paid_stubs.py`. Each matches its protocol in
  `providers/base.py` and currently raises a `FatalError` pointing here, so the chain falls through
  to the free adapter listed after it in `config/providers.yaml`. A stub can never silently change
  quality.
- Implementing one means a single file (an adapter class), one line in the registry, and its entry
  in the `paid` profile.

## Options per stage

| Stage | Free (used) | Paid candidates | What paying buys | Adapter shape |
|---|---|---|---|---|
| Script / storyboard | Gemini Flash (free tier) | Gemini paid tier; Claude Sonnet / Opus | Higher limits; data not used for training | sync `generate_json` |
| Narration | Gemini Flash TTS (10 requests/day) | Gemini TTS paid tier; ElevenLabs (stock voices only, no cloning) | No batching workaround; finer prosody control | sync `synthesize` |
| Keyframes | FLUX.2 klein 4B (Workers AI) | Gemini image (Nano Banana); FLUX.2 pro / flex | Stronger multi-reference character consistency; image editing | sync `generate(…, refs)` |
| Moving shots | Wan 2.2 TI2V-5B on a Kaggle T4 | **the same Wan code on a rented L40S / A100**; Wan 2.2 A14B; Gemini video | 720p–1080p, bf16, no T4 queue, minutes instead of hours | async `submit` / `status` / `collect` |
| Music | ACE-Step 1.5 on Kaggle | ACE-Step on a rented GPU; Lyria | Higher fidelity; longer coherent cues | async, as above |
| Assembly | FFmpeg (local) | unchanged | — | — |

The cheapest upgrade is usually **the same open models on a rented GPU**. The Kaggle kernels are
plain Python scripts that read `jobs.json` and write `results.jsonl`, so they run unchanged on any
CUDA machine.

## Rules

1. **Prices change often.** Read each provider's list price at the time of use and write it, with the
   URL and the date, into `config/prices.yaml`. The same file feeds the "list-price equivalent"
   column in COSTS.md; an unchecked price shows as "unknown", never 0.
2. **Check before adopting:** the licence and output terms; watermarking and provenance (SynthID,
   C2PA, which are never stripped); data retention. Add a row to ETHICS.md §6.
3. **Budget guards:** a per-run spending cap in config; the run stops before it would pass the cap.
4. **No real likeness or voice**, on any lane: cartoons from text, stock voices, no photo uploads,
   no cloning (ETHICS.md §1).

## Benchmark protocol (if a key becomes available)

Take the same shot (s09 or s10), with the same keyframe and the same motion prompt, and generate it
with Wan on a Kaggle T4 and with a paid model. Log cost, latency and resolution, then run a blind
A/B preference test with at least 5 people (random order, "which do you prefer and why"). Record
the votes and quotes in EXPERIMENTS.md, and say whether the difference matters for this audience.
