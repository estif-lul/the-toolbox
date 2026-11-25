# COSTS — measured latency, GPU minutes, list-price equivalent

The tables in sections 1–3 are generated from `runs.jsonl` by `make costs` (Step 6). Only
`model_call` lines count as calls; `cache_hit`, `retry`, `fallback` and `external_job` lines are
counted separately. The free lane costs $0; the list-price column says what the same calls would
cost on a paid plan (prices in `config/prices.yaml`, with source URL and date; unknown prices show
as "unknown", never as 0).

## 1. Per stage
*(generated in Step 6)*

## 2. Per model
*(generated in Step 6)*

## 3. Whole film
*(generated in Step 6)*

---

## 4. Free tiers as found (manual)

Checked 2026-11-25 (Step 0). "Documented" = read from the provider's page; "observed" = seen in
our own calls; **[ME]** = only visible in my account dashboard.

### Gemini API (key from Google AI Studio)
Limits read from my project's AI Studio rate-limit page (signed in) on 2026-11-25 at 14:57 EAT,
Free tier. "Used" is the peak shown for the last 28 days, i.e. today's Step 0 smoke calls.

| Model | Used for | Status | RPM | TPM | **RPD** | Used today |
|---|---|---|---|---|---|---|
| `gemini-3.8-flash` | storyboard draft | 503 "high demand" in all 3 smoke runs, 14:20–14:48 EAT (F05) | 5 | 250K | **20** | 7 |
| `gemini-3.5-flash-lite` | text fallback | works: 1.2–2.5 s, ~21 in / 5–9 out tokens | 15 | 250K | **500** | 2 |
| `gemini-3.8-flash-tts` | narration | works via the Interactions API (F03): ~8.7 s per short line | 3 | 10K | **10** | 2 |
| `gemini-3.8-flash-lite-tts` | TTS fallback | works: 4.5–5.8 s per short line | 3 | 10K | **10** | 2 |

- **Failed requests count.** All 6 logged calls to `gemini-3.8-flash` were 503 errors, and AI Studio
  counts 7 against the 20/day. (The 7th is not in runs.jsonl: possibly a request that timed out on
  our side but still reached the server, or a retry inside the SDK.) So retries on an overloaded
  model burn the daily quota: the config now caps 3.8 Flash at 2 attempts.
- **TTS is the binding constraint: 10 requests/day per model**, 20/day across both TTS models,
  resetting 11:00 EAT. One narration pass with one request per line (~15 lines) would not fit in a
  day. Step 2 must batch lines into fewer requests (PLAN.md "Step 0 findings").
- Pacing in config/providers.yaml = 60 / RPM: 13 s (3.8 Flash), 4 s (Flash-Lite), 21 s (both TTS).
- A full `make smoke` costs 1 request of each TTS model's 10/day and up to 2 of 3.8 Flash's 20;
  during development, run only the checks needed (`make smoke ONLY="flux2 kaggle"`).

- Documented (aistudio.google.com/docs/rate-limits, read 2026-11-25): no per-model free-tier
  numbers are published any more ("Rate limits depend on a variety of factors (such as your usage
  tier) and can be viewed in Google AI Studio"). Limits are **per project, not per key**; daily limits
  (RPD) **reset at midnight Pacific time** (= 11:00 EAT). Tiers: Free (active project) → Tier 1
  (billing linked) → Tier 2/3 (cumulative spend). The only free-tier row on the page is for an
  unrelated API.
- The project's own numbers are only on the signed-in page
  https://aistudio.google.com/rate-limit (**[ME]**). Also, when a 429 arrives, its `QuotaFailure` details
  name the exact metric and limit; `retry.py` logs the full error text, so the first real limit hit
  will record the number in runs.jsonl.
- Until the real RPM is known, the TTS adapters pace themselves at one call per 6 s
  (`min_interval_s: 6` in config/providers.yaml). Narration is ~15 lines, so ~90 s per full pass.

### Cloudflare Workers AI
- Documented (developers.cloudflare.com/workers-ai/platform/pricing, page dated 2026-11-18):
  **10,000 neurons per day** on the Workers Free plan; all limits **reset at 00:00 UTC (03:00 EAT)**;
  over the limit, requests fail with an error. Paid: $0.011 per 1,000 neurons.
- Per image at 1024×1024 (computed from the documented per-tile rates):

| Model | Neurons per image | Images per free day | List price per image |
|---|---|---|---|
| FLUX.2 klein 4B, text only | 4 output tiles × 26.05 = **104.2** | **~96** | $0.00115 |
| FLUX.2 klein 4B + one 1024² reference | 104.2 + 4 × 5.37 = **125.7** | ~79 | $0.00138 |
| FLUX.2 klein 4B + two references | 147.2 | ~67 | $0.00162 |
| FLUX.1 schnell, 4 steps | 4 × 4.80 + 4 × 9.60 = **57.6** | **~173** | $0.00063 |

- That matches the brief's "roughly 50–170 images". Step 3 plans ~70 images, so it needs most of
  one day's allowance with references, or two days.
- Observed (runs `20261125-144547-072d`, `20261125-144741-8d9d`), all 1024×1024 JPEG, 4 steps:

| Call | Latency |
|---|---|
| FLUX.1 schnell (no seed, F06) | 2.9 s, then 24.4 s |
| FLUX.2 klein 4B, text only | 6.6 s, 9.1 s, 6.7 s, 14.0 s |
| FLUX.2 klein 4B + 1 reference | 4.9 s, 11.2 s |

  Latency roughly doubled between 14:45 and 14:48 EAT, so it depends on load; Step 3 should batch.
  Step 0 made 6 klein images (2 with a reference) and 2 schnell images (+1 rejected, F06):
  ≈ 6 × 104 + 2 × 22 + 2 × 58 ≈ 785 neurons (~8% of a day). The dashboard's own neuron count can be checked under Workers AI → Usage **[ME, optional]**.

### Kaggle
- Observed: CLI authentication works with the new-style `KAGGLE_API_TOKEN` (kaggle CLI 2.2.5;
  `kernels list --mine` in 2.6–5.4 s, no GPU used). Phone verification: done (my account settings).
- **Weekly accelerator quota** (`kaggle quota`, saved in `outputs/smoke/kaggle_quota.json`):
  **GPU 30.00 h** and TPU 20.00 h, 0 used, **refresh 2026-11-28 00:00 UTC**. That is after the
  deadline, so these 30 GPU hours are the whole budget for the project.
- The "Daily $10 / Monthly $100 available" shown in Kaggle settings is **not GPU time**: `kaggle
  benchmarks quota` identifies it as the "Model Proxy (AI inference) spend quota, in USD". It is
  unused ($0.00). It might give access to frontier models for the ceiling comparison (to check in Step 6).
- Accelerators (from the CLI, kaggle 2.2.5): `kaggle kernels push --accelerator NvidiaTeslaT4`
  ("GPU T4 x2") or `machine_shape` in kernel-metadata.json. **P100 is retired**: a request for it
  silently runs on a T4 instead. This removes the "P100 instead of a T4" risk in PLAN.md §8.

### Local
- FFmpeg 9.0.1 (gyan.dev full build): the Ken Burns smoke clip (2 s, 1024², 24 fps, 4× upscale)
  rendered in 1.31 s.
