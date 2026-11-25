# FAILURES — what broke, what I tried, what fixed it

Written when each failure happens. Template:

```
## F03 — <stage>: <symptom in a few words>
- When / run_id:
- Symptom (exact error text):
- Cause (verified or suspected):
- Tried: 1) … 2) …
- Resolution / workaround:
- Time lost:  Lesson:
```

---

## F01 — setup: `kaggle` 2.2.5 cannot be imported (`No module named 'six'`)
- When / run_id: 2026-11-25 ~14:05 EAT, Step 0, `uv add kaggle`; before any run.
- Symptom: `import kaggle` →
  `File ".../kaggle/models/upload_file.py", line 22, in <module>: import six` →
  `ModuleNotFoundError: No module named 'six'`.
- Cause (verified): kaggle 2.2.5 imports `six` but does not declare it as a dependency. Older
  environments had `six` installed through other packages, so the bug was hidden; a fresh uv
  environment on Python 3.12 does not.
- Tried: 1) `uv add six` → import and `kaggle --version` work (`Kaggle CLI 2.2.5`).
- Resolution: `six` is an explicit dependency in `pyproject.toml` (pinned in `uv.lock`).
- Also noted: `import kaggle` authenticates **at import time** and prints instructions if no
  credentials exist. The pipeline therefore calls the Kaggle **CLI** in a subprocess and never
  imports the package, so a stranger without Kaggle keys can still run every other stage.
- Time lost: 5 min. Lesson: a fresh, locked environment finds undeclared dependencies early;
  keep `uv.lock` committed so the clean-clone test reproduces exactly this set.

## F02 — keyframes: Cloudflare rejects the key (`Invalid format for Authorization header`)
- When / run_id: 2026-11-25 ~14:10 EAT, Step 0, first Cloudflare request (token verify + model
  search, before any image call).
- Symptom: `GET /user/tokens/verify` → HTTP 400
  `{"code":6003,"message":"Invalid request headers","error_chain":[{"code":6111,"message":"Invalid format for Authorization header"}]}`;
  `GET /accounts/{id}/ai/models/search` → HTTP 400 `{"code":9106,"message":"Authentication failed (status: 400)"}`.
- Cause (verified by the error code and the key's shape): the value saved in `.env` as
  `CLOUDFLARE_API_KEY` is a 37-character **Global API Key**, not an API token. The Global key only
  works with `X-Auth-Email` + `X-Auth-Key` headers and grants full control of the whole account.
- Tried: 1) Bearer auth with the Global key: rejected as above.
  2) Not tried on purpose: `X-Auth-Email`/`X-Auth-Key`. It would work, but it would put an
  all-powerful credential (and my account email) into a media pipeline.
- Resolution: create a scoped **Workers AI API token** (dashboard → Workers AI → "Use REST API"
  → "Create a Workers AI API Token") and store it as `CLOUDFLARE_API_TOKEN`. `env.py` still accepts
  `CLOUDFLARE_API_KEY` as an alias for the token, and `.env.example` warns against the Global key.
  **Resolved 14:44 EAT:** with the scoped token, `make models` lists 6 text-to-image models and
  every FLUX smoke check passes (run `20261125-144741-8d9d`). The Global key was removed from `.env`.
- Time lost: 35 min of waiting (the rest of Step 0 continued meanwhile). Lesson: least privilege.
  Every credential in `.env` should be able to do only what its stage needs.

## F03 — narration: the brief's TTS model "does not exist" (`404 NOT_FOUND`)
- When / run_id: 2026-11-25 ~14:12 EAT, Step 0, model verification before the smoke test.
- Symptom: `client.models.list()` returns 28 models and **no TTS model at all**.
  `client.models.get("gemini-3.8-flash-tts")` → `404 NOT_FOUND. Model is not found: models/gemini-3.8-flash-tts`.
  The same 404 for 15 other plausible ids (`gemini-3.8-flash-preview-tts`, `gemini-2.5-flash-preview-tts`,
  `gemini-3.1-flash-tts-preview`, `gemini-2.5-pro-preview-tts`, …).
- Cause (verified from the docs): the speech-generation docs (now at
  `aistudio.google.com/docs/speech-generation`; the old `ai.google.dev` URL redirects) say TTS now
  goes through the **Interactions API** (`client.interactions.create`, `response_format={"type":"audio"}`,
  `generation_config.speech_config=[{"voice": ...}]`, style as a `speech_metadata` annotation), not
  `generate_content` with `response_modalities=["AUDIO"]` as in older guides.
  The TTS models are not visible to the models endpoint. Current ids: `gemini-3.8-flash-tts` and
  `gemini-3.8-flash-lite-tts`.
- Tried: 1) metadata lookups of 16 ids (all 404). 2) Read the docs. 3) Interactions API with
  `gemini-3.8-flash-tts`, voice Kore → **works** (run `20261125-142010-cc5c`): a complete WAV,
  24 kHz, mono, 16-bit, 2.23 s for "Testing one two three.", latency 8.6 s.
  4) The same with `gemini-3.8-flash-lite-tts` → works (1.65 s, latency 5.8 s).
- Resolution: `pipeline/providers/gemini_tts.py` uses the Interactions API; the chain is
  Flash TTS → Flash-Lite TTS (config/providers.yaml). The docs confirm Amharic is supported by both;
  checked by ear in Step 2 (E18).
- Time lost: 20 min. Lesson: "the model isn't listed" is not proof it's gone. Read the current
  docs before concluding, and keep the adapter as the only place that knows the API's shape.

## F04 — text: no "Gemini 3.8 Flash-Lite" text model is served
- When / run_id: 2026-11-25 ~14:12 EAT, Step 0, `client.models.list()`.
- Symptom: `gemini-3.8-flash` is listed, but the newest Flash-Lite text model listed is
  `gemini-3.5-flash-lite` (also `gemini-3.1-flash-lite`, `gemini-2.5-flash-lite`). There is a
  `gemini-3.8-flash-lite-tts`, but no 3.8 Flash-Lite for text.
- Cause: the brief's "Gemini 3.8 Flash, Flash-Lite for bulk calls" names the family, not an exact id.
- Resolution: the text fallback is `gemini-3.5-flash-lite` (smoke: `{"ok": true}`, 2.5 s, 21/9 tokens).
  Full listing in `outputs/smoke/models_gemini.json`.
- Time lost: 2 min.

## F05 — text: `gemini-3.8-flash` answers `503 UNAVAILABLE` (high demand)
- When / run_id: 2026-11-25 14:20 EAT, run `20261125-142010-cc5c`, smoke check `text`.
- Symptom: `ServerError: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently
  experiencing high demand. Spikes in demand are usually temporary. Please try again later.'}}`
  on attempt 1 (after 22.4 s) and attempt 2 (1.7 s).
- Cause: provider-side load on the free tier (not our request: the same prompt worked on Flash-Lite).
- What the pipeline did (as designed, visible in runs.jsonl): `model_call` error → `retry` (waited
  2.3 s) → `model_call` error. In the smoke test each model is tested alone, so it stopped there; in
  a real stage the chain continues to the `fallback` (Flash-Lite), which answered in 2.5 s.
- Re-checked: run `20261125-142645-32c4` (14:26 EAT): still 503 on both attempts; attempt 2
  took **104.5 s** to fail. A one-off probe of `gemini-3.7-flash` (same prompt, 1 attempt) also
  returned 503 after 5.0 s. So the whole Flash tier was overloaded, while Flash-Lite answered.
- Resolution: keep the chain 3.8 Flash → 3.5 Flash-Lite (no 3.7 middle step: it fails the same
  way under the same load). Text is first needed in Step 1 (the storyboard draft); if 503s persist
  then, the draft runs on Flash-Lite and runs.jsonl shows the fallback.
- Follow-up done: a 104 s wait before a 503 is expensive, so `gemini_text` now sets a 60 s client
  timeout (`timeout_s` param). Third run `20261125-144741-8d9d` (14:47 EAT): still 503, the slow
  attempt now ends at 57 s; Flash-Lite answered in 1.2 s.
- Lesson: on free tiers, a 503 at the worst moment is normal; it's why every stage has a chain.
- Still happening in Step 1 (2026-11-25, 15:46–15:49 EAT, runs `20261125-154638-d856` and
  `20261125-154916-fae2`): 5 more 503s from 3.8 Flash (each answered in 2–4 s); with the 20 K-char
  storyboard prompt, Flash-Lite **also** answered 503 three times in a row (15:47). The older
  `gemini-3.5-flash` (listed for this key in `outputs/smoke/models_gemini.json`) answered at the
  first try (64 s). It is now the middle step of the `script` chain (3.8 Flash with 1 attempt →
  3.5 Flash → 3.5 Flash-Lite): one attempt on a model that is 503 all day saves its 20/day quota.

## F06 — keyframes: FLUX.1 schnell rejects `seed` (HTTP 400)
- When / run_id: 2026-11-25 14:45 EAT, run `20261125-144459-1bfd`, smoke check `flux1`.
- Symptom: `HTTP 400: {"errors":[{"message":"AiError: Bad input: Error: Additional or unevaluated
  properties '/seed' at '/' not allowed (…)","code":5006}],"success":false}`.
- Cause (verified): the Workers AI input schema for `@cf/black-forest-labs/flux-1-schnell` has only
  `prompt` (1–2048 chars) and `steps` (max 8, default 4), with `additionalProperties: false`. The
  example on Cloudflare's own model page sends a `seed`, which the schema rejects. There is also no
  width/height: output is always 1024×1024 JPEG.
- Tried: 1) without `seed` → ok, 1024×1024 JPEG in 2.9 s (run `20261125-144547-072d`).
- Resolution: the adapter sends `seed` only to models that accept it (`send_seed`, off for schnell);
  the log records `seed: null` for schnell calls, and `tests/test_cloudflare.py` pins the request shape.
- Consequence: schnell images can't be reproduced from a seed at all. As a fallback it is still fine
  (the chosen file is cached), but plan B in Step 3 ("text-only + fixed seed") loses its fixed seed.
- Time lost: 5 min. Lesson: trust the schema over the example.

## F07 — keyframes: FLUX.2 klein ignores the seed for reproducibility (same seed, different image)
- When / run_id: 2026-11-25 14:45 EAT, runs `20261125-144547-072d` and `20261125-144741-8d9d`,
  smoke checks `flux2` vs `flux2_repeat`.
- Symptom: same prompt, same `seed=42`, same steps (4) and size → **different images** both times
  (mean absolute pixel difference ≈ 50/255 per channel in the first pair). Similar composition (red
  apple, worn wooden table), but different light (a window appears) and table grain.
- Cause (suspected): the multipart `seed` field is not honoured by the Workers AI klein endpoint, or
  inference is not deterministic there. The model page documents no body fields, so it can't be checked.
- Resolution: reproducibility comes from the **cache**, not from re-generation: a chosen keyframe is
  kept by file (`keyframe_choice` → manifest → path, committed in `outputs/`). A clean clone gets
  cache hits and the identical film; regenerating a shot produces a new variant, which is
  expected and is how the walkthrough's "change one shot" works. ARCHITECTURE.md must say this.
- Lesson: "fixed seed = same image" is a property of a provider, not of diffusion in general. Test it.

## F08 — script: Gemini refuses the storyboard schema as an output constraint (`too many states`)
- When / run_id: 2026-11-25 15:46 EAT, run `20261125-154638-d856`, `make script` (first run).
- Symptom: on `gemini-3.5-flash-lite` (3.8 Flash had answered 503, F05): `400 INVALID_ARGUMENT.
  The specified schema produces a constraint that has too many states for serving. Typical causes
  of this error are schemas with lots of text (for example, very long property or enum names),
  schemas with long array length limits (especially when nested), or schemas using complex value
  matchers (for example, integers or numbers with minimum/maximum bounds …)`.
- Cause (verified by the fix): `response_json_schema` is compiled into a decoding state machine.
  Our first converted copy still had ~50 numeric bounds (seeds, durations, crop focus, ducking),
  array length limits (8–12 shots, 2 layers) and every description.
- Tried: 1) the schema minus the keywords Gemini doesn't list → 400 as above. 2) the planned
  fallback, no constraint at all (JSON mode, schema only in the prompt) → never reached a model
  that was up (503 on every attempt, F05). 3) a **structural** constraint only: types, required
  fields, closed objects (`additionalProperties: false`), enums and `$ref`s; no bounds, no
  lengths, no descriptions (6.9 K chars). The full schema still goes in the prompt text →
  accepted by `gemini-3.5-flash`, and the draft had **0 schema errors** (run `20261125-154916-fae2`).
- Resolution: `pipeline/script.py` `gemini_schema()` keeps only the structure; the full schema is
  checked afterwards by our own validator (`make validate` rules), which is the real contract.
  The no-constraint retry stays as the fallback for any other 400 that mentions the schema.
  `tests/test_script.py` pins what the constraint may contain.
- Time lost: 15 min, 9 requests (5 of them on 3.8 Flash's 20/day).
- Lesson: an output constraint is a hint to the decoder, not a validator. Send the shape, check the
  details yourself.

## Positive result worth recording — FLUX.2 klein reference images work
- Run `20261125-144547-072d`: `flux2_ref` with `input_image_0 = flux2.jpg` and the prompt "the same
  red apple from the reference image, now on a blue ceramic plate" kept the same apple, the same
  table and even the same knot in the wood, and added the plate. So plan **A** for Step 3
  (reference sheets passed into every keyframe) is available, at ~22 extra neurons per 1024² reference.
