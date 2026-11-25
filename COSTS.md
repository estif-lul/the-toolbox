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
| Model | Used for | Status | Free-tier limits |
|---|---|---|---|
| `gemini-3.8-flash` | storyboard draft | works, but 503 "high demand" twice on 2026-11-25 14:20 (F05) | RPM / RPD **[ME]: read from aistudio.google.com/rate-limit** |
| `gemini-3.5-flash-lite` | text fallback | works: 2.45 s, 21 in / 9 out tokens | **[ME]** as above |
| `gemini-3.8-flash-tts` | narration | works via the Interactions API (F03): 8.6 s for a 2.2 s line | **[ME]** as above |
| `gemini-3.8-flash-lite-tts` | TTS fallback | works: 5.8 s for a 1.7 s line | **[ME]** as above |

- Documented: the rate-limits page no longer publishes per-model free-tier numbers; it says they
  are shown per project in AI Studio. Limits are **per project, not per key**, and daily limits
  (RPD) **reset at midnight Pacific time** (= 11:00 EAT).
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
- Observed: *(smoke test pending the scoped API token, F02)*.

### Kaggle
- Observed: CLI authentication works with the new-style `KAGGLE_API_TOKEN` (kaggle CLI 2.2.5;
  `kernels list --mine` in 5.4 s, no GPU used).
- Weekly GPU quota: **[ME]: read from kaggle.com → Settings → "GPU" quota** (the brief says
  about 30 h/week). Phone verification status: **[ME]: confirm in Settings** (needed for GPU and
  internet in kernels; first needed in Step 4).

### Local
- FFmpeg 9.0.1 (gyan.dev full build): the Ken Burns smoke clip (2 s, 1024², 24 fps, 4× upscale)
  rendered in 1.31 s.
