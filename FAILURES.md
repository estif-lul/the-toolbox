# FAILURES — what broke, what I tried, what fixed it

Written when each failure happens. Template (PLAN.md §13):

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
  **Status: waiting for the new token** (the rest of Step 0 continued meanwhile).
- Time lost: 10 min. Lesson: least privilege. Every credential in `.env` should be able to do
  only what its stage needs.

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
  `generate_content` with `response_modalities=["AUDIO"]` as in older guides and in PLAN.md.
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
- Follow-up: a 104 s wait before a 503 is expensive. Step 1 should set a client timeout on the
  text call (~60 s) so the fallback starts sooner.
- Lesson: on free tiers, a 503 at the worst moment is normal; it's why every stage has a chain.
