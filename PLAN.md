# PLAN — "The Toolbox" (Heritage Short)

Working plan for the B2W0 AI-Content Generation challenge. Each step is meant to be executed in
its own session. Start a session with:

> Read PLAN.md (and the files listed under the step's "Inputs"), then do Step N.

**Deadline:** Thursday 26 Nov 2026, 23:59 EAT, for both assignments. Internal target: submit by 22:30.

Legend: **[ME]** = something only I (the human) can do · **[VERIFY]** = a fact from the brief or
from memory that must be checked against the live service before relying on it (models and free
tiers move fast; anything that changed goes in FAILURES.md).

---

## 0. Decisions (locked)

| Topic | Decision |
|---|---|
| Story | **"The Toolbox"**: the tools in Dad's red toolbox each open a memory of something he taught me (car, woodwork, electricity, plumbing) in our Habesha family home. Recurring line *"እስኪ እንየው"* ("Let's look at it first"). The proverb *"ቀስ በቀስ እንቁላል በእግሩ ይሄዳል"* marks my growing up. Ending: I fix something myself and call him: *"Dad, I fixed it myself."* He answers *"ጎበዝ ልጄ"* ("Well done, my son"). Full details in §3. |
| Audience | Friends and family (Habesha), watching on phones, shared via WhatsApp/Telegram/social |
| Characters | **Cartoon characters only.** No photo, likeness or voice of any real person is used as input or reproduced. Dad is a Habesha man (early 40s in the memories, about 50 now); the narrator is a cartoon version of me (male) at three ages (child, teen, adult). |
| Narration | English narration, Gemini TTS **stock voices** (no cloning). A second stock voice speaks Dad's 3 short Amharic lines (English fallback if the Amharic TTS is poor). |
| Subtitles | English, burned in (Dad's Amharic lines get English translations), plus a sidecar `.srt` |
| Video | Wan 2.2 TI2V-5B on Kaggle, automated with `kaggle kernels push` / `status` / `output`. Ken Burns fallback for every shot. |
| Music | ACE-Step 1.5 on Kaggle, 3 instrumental candidates; one chosen with written reasons |
| Master format | **Square 1:1 masters** (keyframes 1024×1024, subject centred) cropped to 9:16 and 16:9 at assembly. Finals at 720×1280 and 1280×720, 24 fps. |
| Stack | Python 3.12 via uv (3.14 is installed but some wheels lag), FFmpeg 9 (installed), GNU Make (installed), pytest. No Remotion. |
| One command | `make film` (thin wrapper around `uv run python -m pipeline.run film`, which also works without Make) |
| Accounts | **[ME]** created when each step needs them: Gemini (AI Studio), Cloudflare, Kaggle (phone-verified), GitHub |
| Future | Paid/frontier lane designed in from Step 0 as a provider profile (§10) |
| Coding agent | Claude Code (state this in the report; the brief lists free agents but allows others) |

### Ethics stance (recorded in ETHICS.md in Step 0, before any generation)
- The characters are fictional cartoons *inspired by* my father. None of his photos, likeness or
  voice is used. ETHICS.md says this explicitly.
- I still record **my father's agreement to the story being told** (date, medium: a WhatsApp or
  voice message is enough). The zero-score gate covers any real person "shown or voiced", so this
  is a cheap safeguard. **[ME]**
- Other family members appear only as unnamed background cartoon figures. ETHICS.md notes this.
  If a specific relative is meant to be recognisable, their agreement is recorded too.
- No private details in prompts sent to free endpoints: no real names (beyond "Dad"), addresses,
  licence plates, workplaces or phone numbers.
- Style is described by qualities (warm, hand-painted, soft light), never by naming a living artist or studio.

---

## 1. Global conventions (apply to every step)

### 1.1 Repository layout (target)

```
README.md               one command, what it does, what it costs
PLAN.md                 this file
storyboard.json         THE contract between all stages
schema/storyboard.schema.json
config/
  providers.yaml        provider profiles: free (default) and paid
  prices.yaml           list prices for the cost-equivalent column (filled in when verified)
pipeline/
  __init__.py
  run.py                CLI orchestrator: smoke|validate|script|narration|radio|refs|keyframes|kenburns|shots|music|assemble|film|costs
  common/
    log.py              log_call() -> runs.jsonl
    cache.py            cache keys, manifests, staleness
    retry.py            backoff + Retry-After + fallback chains
    storyboard.py       load + JSON Schema validation + semantic checks + timeline math
    ffmpeg.py           command builders + runner (dry-run printable)
    env.py              .env loading, helpful "missing key" errors
  providers/
    base.py             Protocols: TextProvider, TTSProvider, ImageProvider, VideoProvider, MusicProvider
    registry.py         get_provider(stage, profile) from config/providers.yaml
    gemini_text.py  gemini_tts.py  cloudflare_image.py  kenburns.py
    kaggle_wan.py  kaggle_acestep.py
    paid_stubs.py       documented stubs for the paid lane (§10)
  smoke.py  script.py  narration.py  keyframes.py  shots.py  music.py  assemble.py  costs.py
  kaggle/
    wan_kernel/         kernel-metadata.json + wan_job.py (templated at push time)
    acestep_kernel/     kernel-metadata.json + acestep_job.py
tests/                  pytest: schema, cache keys, timeline, subtitles, ffmpeg builders
scripts/check_secrets.py
assets/fonts/           OFL font for subtitles and end card (+ its licence file)
outputs/                kept in git so the run can be inspected (keep each file < 50 MB)
  smoke/ refs/ keyframes/ kenburns/ shots/ music/ narration/ segments/ cuts/ final/
runs.jsonl              one line per model call (+ cache-hit/fallback events)
DESIGN.md ARCHITECTURE.md EXPERIMENTS.md FAILURES.md COSTS.md ETHICS.md
docs/PAID_LANE.md  docs/REPORT_DRAFT.md  docs/WALKTHROUGH_SCRIPT.md  docs/POST_DRAFT_NOTES.md
.env.example  .gitignore  Makefile  pyproject.toml  uv.lock
```

### 1.2 The contract
- `storyboard.json` is the only thing stages share as *intent*. Stages share *artifacts* through
  per-stage manifests (`outputs/<stage>/manifest.json`).
- Every run starts with `validate`: JSON Schema (Draft 2020-12) plus semantic checks (§2.2). An
  invalid storyboard stops the run before any model call.
- Stages never read each other's code or private state; they only read the storyboard, upstream
  manifests and files.

### 1.3 Caching (what makes "change one shot, regenerate only that shot" true)
- `cache_key = sha256(canonical_json({stage, stage_version, provider, model, params, seed, inputs, upstream_hashes}))`, where canonical means sorted keys, no whitespace and UTF-8.
  - `inputs` holds only the storyboard fields that stage actually uses. For example, narration
    uses `text`, `voice` and `style`, not the image prompt.
  - `upstream_hashes` holds the content hashes (sha256 of bytes) of the files consumed. For
    example, a Wan job consumes the keyframe's hash.
- Artifact path: `outputs/<stage>/<shot_id>/<cache_key[:16]>.<ext>`. Old versions are kept so they
  can be compared in experiments.
- `outputs/<stage>/manifest.json`: `{shot_id: {cache_key, path, sha256, provider, model, created_at, status}}`.
- A stage computes the expected key for each shot. If the manifest has it and the file exists, it
  is a **cache hit**, logged as an event with no model call. Otherwise it is generated.
- `FORCE=1` (or `--force s05`) regenerates regardless.
- Bumping `stage_version` in code invalidates that stage when its logic changes.
- The expected effect of each change (unit tests assert this):
  - edit the narration text of s05 → 1 TTS call for s05, then reassembly (FFmpeg only)
  - edit the image prompt of s05 → 1 keyframe call for s05 + its Ken Burns clip. The s05 Wan clip
    becomes *stale*; assembly uses the Ken Burns clip for s05 until `make shots` is run again.
  - edit the style block → every keyframe changes (expected and documented)

### 1.4 Logging: `runs.jsonl`
Each line is one JSON object:
```json
{"ts":"2026-11-25T12:00:00+03:00","run_id":"20261125-120000-ab12","event":"model_call",
 "stage":"narration","shot_id":"s05","provider":"gemini_tts","model":"<id>",
 "params":{"voice":"Kore","style":"warm, unhurried"},"seed":null,
 "input_hash":"…","cache_key":"…","output":"outputs/narration/s05/….wav",
 "latency_s":3.42,"gpu_s":null,"cost_usd":0.0,"list_price_usd":0.0012,
 "attempt":1,"status":"ok","error":null}
```
- `event` ∈ `model_call | cache_hit | fallback | stale | retry | external_job` (Kaggle push/pull).
- Only `model_call` lines count as calls in COSTS.md; the other events exist so the walkthrough can
  show "one new model call, everything else cache hits".
- Never log secrets. Prompts are logged by hash and stored in full in the storyboard, which is already public.

### 1.5 Retries and fallbacks
- `@with_retry(max_attempts=3, base=2s, factor=2, jitter, respect Retry-After)` retries on
  429, 5xx, timeouts and connection errors. 4xx validation errors fail fast.
- When retries run out, try the stage's `fallback` provider from `providers.yaml`, logged as a
  `fallback` event:
  - **text:** Flash → Flash-Lite
  - **image:** FLUX.2 klein → FLUX.1 schnell
  - **video:** Wan → Ken Burns (always available, local)
  - **music:** ACE-Step → previous cached candidate → code-generated pad (last resort; documented)
  - **tts:** primary TTS model → alternate TTS model id **[VERIFY]** → stop with a clear error.
    There is no silent narration fallback.
- Limit per shot: 3 creative attempts (different prompt or seed) before using the fallback, per Appendix B.

### 1.6 Secrets
- `.env` (gitignored) holds: `GEMINI_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`,
  `KAGGLE_USERNAME`, `KAGGLE_KEY` (or `~/.kaggle/kaggle.json`), `PROFILE=free`.
- `.env.example` is committed with blank values and comments saying where each key comes from.
- `scripts/check_secrets.py` scans tracked files for key patterns (e.g. `AIza…`, long hex or
  base64 tokens next to "token"/"key"). It runs in `make check` and as a git pre-commit hook
  installed by `make setup`.

### 1.7 Documentation as you go (the grading reads only text and logs)
- Each experiment is added to EXPERIMENTS.md **when it runs**, using the template in §13. Target ≥ 12.
- Each failure is added to FAILURES.md **when it happens**, using the template in §13.
- Each step ends with a commit. Messages say what changed and why
  (e.g. `storyboard: shorten s02 narration after user test 1 (3/4 said intro dragged)`).

### 1.8 Windows notes
- Make recipes run in Git Bash's `sh`; recipes only call `uv run python -m pipeline.run …`, so they are portable.
- FFmpeg `subtitles=` filter: pass a **relative** path with forward slashes and run FFmpeg with the
  repo root as cwd. This avoids `C\:` escaping problems.
- Write files as UTF-8 with no BOM.

---

## 2. The storyboard contract

### 2.1 Shape (the schema is written in Step 1; this is the target)

```json
{
  "schema_version": 1,
  "title": "The Toolbox",
  "logline": "…",
  "format": {"fps": 24, "master_aspect": "1:1", "master_px": 1024,
             "exports": [{"name":"9x16","w":720,"h":1280},{"name":"16x9","w":1280,"h":720}],
             "target_duration_s": {"min": 60, "max": 90}},
  "style": {"block": "warm hand-painted 2D cartoon, soft golden light, gentle textures, rounded shapes, muted earthy palette with teal accents",
            "negative": "text, letters, watermark, logo, photorealistic, extra fingers, deformed hands",
            "reference_choice": null},
  "characters": [
    {"id": "dad", "description": "…fixed text attached to every prompt that features him (§3.4)…", "seed": 1101, "reference_choice": null},
    {"id": "dad_now", "description": "…", "seed": 1102, "derived_from": "dad", "reference_choice": null},
    {"id": "me_child", "description": "…", "seed": 1201, "reference_choice": null},
    {"id": "me_teen",  "description": "…", "seed": 1202, "reference_choice": null},
    {"id": "me_adult", "description": "…", "seed": 1203, "reference_choice": null}
  ],
  "voices": {
    "narrator": {"voice": "<stock voice>", "style": "warm, unhurried, a quiet smile in the voice"},
    "dad":      {"voice": "<stock voice>", "style": "calm, deep, patient"}
  },
  "music": {
    "cues": [{"id": "main", "from_shot": "s01", "to_shot": "s10",
              "intent": "gentle, nostalgic, room for the voice; theme returns warmer at the end",
              "caption": "…", "bpm": 80, "key": "D major", "instrumental": true,
              "seeds": [301, 302, 303]}],
    "chosen": {"main": null},
    "duck": {"threshold": 0.02, "ratio": 6, "attack_ms": 300, "release_ms": 1500}
  },
  "shots": [
    {"id": "s01", "beat": "motif", "reason": "…why this shot exists…",
     "shot_size": "close-up", "camera": "static", "characters": [],
     "image_prompt": "…subject + setting only; style block is appended in code…",
     "seed": 2001, "keyframe_choice": null,
     "motion": "wan", "motion_prompt": "…motion + camera only…",
     "kenburns": {"move": "push_in", "amount": 0.08},
     "crop_focus": {"x": 0.5, "y": 0.5},
     "narration": [{"voice": "narrator", "text": "…"},
                   {"voice": "dad", "lang": "am", "text": "እስኪ እንየው", "subtitle": "Let's look at it first.", "tts_text": null}],
     "layers": null,
     "min_duration_s": 4.0, "pad_before_s": 0.4, "pad_after_s": 0.6, "duration_override_s": null,
     "transition_in": "fade_from_black", "priority": 1}
  ],
  "end_card": {"duration_s": 3.0,
               "lines": ["Made with AI", "For Dad, who fixes everything himself",
                         "Characters are fictional cartoons", "Images: FLUX · Video: Wan 2.2 · Music: ACE-Step · Voice: Gemini TTS"]}
}
```

Field notes:
- `*_choice` fields hold the **index of the chosen candidate** (e.g. `2`), never a file path. The
  manifest resolves the index to a file, so the storyboard stays portable and stays the contract.
- `image_prompt` is the subject and setting only. The final prompt is built in code:
  `{image_prompt}. {character descriptions for shot.characters}. Style: {style.block}`.
  The same wording is used every time to avoid drift.
- `motion_prompt` covers motion and camera only. It never re-describes the subject (Appendix B).
- `priority` sets the order of Wan jobs, so if GPU time runs out the most important shots are already done.
- `narration[]` fields:
  - `lang` defaults to `en`.
  - `subtitle` overrides the subtitle text, used for the English translation of Dad's Amharic lines.
  - `tts_text` overrides what is sent to TTS, for phonetic re-spelling, without touching the subtitles.
  - `{"echo_of": "s05:1", "gain_db": -8, "reverb": true}` reuses another line's audio, which costs no model call.
- `layers` (used by s10 only): `[{"id": "a", "image_prompt": …, "characters": [...], "seed": …}, {"id": "b", …}]`.
  Each layer gets its own keyframe and clip; assembly composites them (`vstack` for 9:16, `hstack`
  for 16:9). Cache keys are per layer.
- `duration_s` is **computed** (`max(min_duration, pad_before + narration + pad_after)`) unless
  `duration_override_s` is set.

### 2.2 Semantic checks (in `common/storyboard.py`, run by `validate`)
1. Shot ids are unique and match `^s\d{2}$`; there are 8–12 shots.
2. Every `characters[]` reference in a shot exists in `characters`.
3. Every narration `voice` exists in `voices`.
4. Every shot has a non-empty `reason`.
5. Total narration is 120–230 words (warning only); the hard check comes after TTS timing exists.
6. Once `outputs/narration/timing.json` exists: total duration plus end card is within 60–90 s,
   otherwise the run fails with a list of the shots to trim.
7. Music cue `from_shot`/`to_shot` exist and cover all shots.
8. No obvious private data. A soft lint flags digit runs that look like phone numbers or plates,
   and emails.
9. `motion: "wan"` shots have a `motion_prompt`; every shot has a `kenburns` move, and consecutive
   shots don't repeat the same move (warning).

---

## 3. Draft story (refined in Step 1, changed by user tests)

Target: about 140 English words + 3 short Amharic lines from Dad (~75–80 s at about 2.3 words/s,
to be measured from the real TTS output) + a 3 s end card, 10 shots.

### 3.1 Given facts (from me)
- I call my father **Dad**. He is **around 50 now**. We are **Habesha (Ethiopian)**. I am **male**.
- He does almost everything himself: the car, woodwork, electricity, plumbing.

### 3.2 Story details (proposed by Claude; swap in true ones wherever they differ)
The audience is family, so a detail they know is true lands harder than an invented one. Keep the
structure and replace any detail below with the real version where it differs.

| Element | Detail | Why it works |
|---|---|---|
| **The toolbox** (motif) | A dented **red** metal cantilever toolbox with scratched paint and a worn black handle. In s09 it is older and more scratched. | The strongest colour in the film; easy to keep consistent; it carries the story from start to end |
| **Home** | A modest Habesha family compound: a single-storey house with cream walls and a corrugated-iron roof, a **sky-blue metal gate**, eucalyptus trees, and a black plastic water tank on a metal stand | Instantly recognisable to an Ethiopian family audience |
| **The car** | An old boxy **white 1980s sedan** (no brand or plate in prompts) | The classic family car many Ethiopian dads keep alive themselves |
| **Woodwork** | He built the **rekebot** (the wooden coffee-ceremony cup stand) that the family still serves coffee on | It ties DIY to a daily family ritual, and links s04 to s05 |
| **Power cut** | A blackout night: candlelight, the **jebena** on a small charcoal stove, coffee being made in the dark, while Dad goes to the fuse box with a torch and a tester | Power cuts are a shared experience; the coffee ceremony makes the scene feel like home |
| **Plumbing** | The leaking pipe on the **water tank** stand, the family's backup when the tap water stops | The water tank is a familiar sight in Ethiopian homes |
| **Hand-over** | When I moved into my own place, **he gave me his old toolbox** | It pays off the motif: the toolbox, and the skills, change hands |

### 3.3 Dad's phrases (in Amharic, spoken by Dad's stock voice, with English subtitles)

| Where | Amharic | Transliteration | Subtitle / meaning | Role |
|---|---|---|---|---|
| s05, echoed in s09 | **እስኪ እንየው** | *Eski, enyew.* | "Let's look at it first." | The recurring line. A natural everyday Amharic phrase ("let's see it"), short enough for TTS |
| s08 | **ቀስ በቀስ እንቁላል በእግሩ ይሄዳል** | *Kes be kes, enqulal be egru yihedal.* | "Slowly, slowly, the egg walks on its own legs." | A well-known Ethiopian proverb about patience and growth. In context it means the boy he raised has become independent |
| s10 | **ጎበዝ ልጄ** | *Gobez, lije.* | "Well done, my son." | The emotional payoff of the whole film |

- The narration stays in English, per the decision. Only Dad speaks Amharic: 3 short lines.
- **Risk:** Gemini TTS pronunciation of Amharic in Ge'ez script **[VERIFY in Step 2]**. I am a
  native speaker, so I judge it by ear (EXPERIMENTS.md E18).
- **Fallback:** Dad's lines in English, in the same stock voice. The subtitles don't change.
- The s09 echo of *"Eski, enyew"* reuses the s05 audio file with a soft reverb and lower volume in
  assembly (FFmpeg `aecho`), so it costs no extra model call.

### 3.4 Characters (one fixed description each; attached word-for-word to every prompt)
Each character has a **colour anchor** that survives ageing and the model's drift: Dad is always in
navy overalls, I am always in mustard yellow, and the toolbox is always red.

| id | Appears in | Description (draft for `storyboard.json`) |
|---|---|---|
| `dad` | s02–s08 (the memories) | "Dad, a Habesha Ethiopian man in his early forties, warm brown skin, short black curly hair just greying at the temples, short neat black beard, kind eyes with laugh lines, medium build, faded navy-blue work overalls with sleeves rolled up, a yellow pencil behind his right ear" |
| `dad_now` | s10 only | "the same man at about fifty, more grey in his hair and beard, the same faded navy-blue work overalls, a pencil behind his ear". He is still fixing something when he answers the phone. Generated **from the `dad` reference** (image edit) if FLUX.2 klein supports references |
| `me_child` | s02, s03, s05, s06 | "a Habesha Ethiopian boy about eight years old, brown skin, short curly black hair, round face, big curious eyes, oversized mustard-yellow T-shirt, khaki shorts, plastic sandals" |
| `me_teen` | s08 | "the same boy at about fifteen, tall and lanky, short curly black hair, a faint moustache, mustard-yellow hoodie with the sleeves pushed up, jeans" |
| `me_adult` | s09, s10 | "the same young man in his mid-twenties, brown skin, short neat curly hair, short trimmed beard, mustard-yellow overshirt over a white T-shirt, dark trousers" |

- Other family members appear only as soft background figures (s05, s06), never as named
  characters, so there are fewer real people to depict and fewer consistency problems.
- **Style block (draft):** "warm hand-painted 2D cartoon illustration, soft golden light, gentle
  paper texture, rounded friendly shapes, earthy palette of ochre, terracotta and eucalyptus green
  with sky-blue accents, cosy and nostalgic, Ethiopian home setting"

### 3.5 Shot list and narration draft

| # | Beat | Shot (subject + setting) | Narration (English) / Dad (Amharic) | Reason |
|---|---|---|---|---|
| s01 | Motif | CU: the red toolbox, closed, on a wooden floor in morning light | "My dad never called anyone to fix anything." | Introduces the object that carries the film |
| s02 | Place | WS: the compound with the sky-blue gate; Dad walks out carrying the red toolbox, the boy following | "If it could be done at home, he did it himself. And I was always one step behind him." | Establishes place, Dad and the boy |
| s03 | Car | MS: Dad lying under the old white sedan, only his legs and arm visible; the boy crouching, holding a torch | "Under our old white car, I held the torch. He held the wrench, and explained every bolt." | Memory 1: the boy as helper |
| s04 | Wood | Insert: Dad's hands planing wood, shavings curling; a finished rekebot with small coffee cups beside it | "From a few planks, he built the rekebot we still serve coffee on." | Memory 2: making, not just repairing |
| s05 | Power cut | MS: night; Dad at the fuse box with a torch and tester, the boy holding a candle beside him; in the soft background, a jebena on a charcoal stove | "When the power went out, everyone said: call someone. Dad just picked up his tester." / Dad: **"እስኪ እንየው"** | Introduces the recurring line |
| s06 | Payoff | WS: night; the house windows light up, the boy jumps with joy, family silhouettes cheer | "And the whole house lit up again." | Emotional lift |
| s07 | Plumbing | CU: water dripping from a pipe joint under the water tank; Dad's hands turn a pipe wrench; the drip stops | "A leaking pipe. A wrench. Patience. Then… silence." | Memory 4: patience. Its quiet sets up the proverb |
| s08 | The turn | MS: the teen tightens a bolt on the white car while Dad watches, arms folded, smiling | "Then one day, he stopped fixing things for me, and started fixing them with me." / Dad: **"ቀስ በቀስ እንቁላል በእግሩ ይሄዳል"** | The learning moment; the proverb names the growth |
| s09 | Motif returns | CU: the adult me opens the same red toolbox, now older, in my own small apartment | "When I moved out, he gave me his old toolbox. Now, when something breaks, I hear him: let's look at it first." (+ echo of "እስኪ እንየው") | The callback that pays off the motif |
| s10 | Ending | **Split screen** composited in code: the adult me on the phone, smiling, a fixed tap behind me \| Dad (`dad_now`) on the phone in his yard, a spanner in his other hand. Stacked top/bottom in 9:16, side by side in 16:9 | "So I call him. Dad, I fixed it myself." / Dad: **"ጎበዝ ልጄ"** / "And I can hear him smiling." | The ending: gratitude and continuity; we finally see him today |
| end | End card | Code-generated card | — | Required AI label |

- English word count is about 140 (≈ 61 s), Amharic lines about 6 s, and padding about 10 s, so
  roughly 77 s + 3 s end card. That is inside 60–90 s with room for test-driven changes.
- **s10 split screen:** two keyframes (`s10a`, `s10b` as sub-images of shot s10) are composited
  with FFmpeg `vstack`/`hstack` per export. **Fallback:** a single shot of me on the phone, with
  Dad heard but not seen.

### 3.6 Still open (needed by Step 2) [ME]
1. Narrator voice: I audition 3 stock voices in Step 2 and pick one.
2. A quick reality check of §3.2 and §3.4: say which details are untrue for my dad or me and give
   the real version (e.g. car colour, what he built, how I look). Optional but it makes the film better.

---

## 4. Step 0: Scaffold, contracts-in-code, smoke test

**Goal:** an empty but real pipeline. Every provider is reachable and logged, audience and ethics
are on record before any generation, and the paid lane is pluggable.
**Time box:** ~1.5 h. **Inputs:** PLAN.md, the brief.

### [ME] before or during this step
- [ ] Gemini API key from Google AI Studio → `.env` `GEMINI_API_KEY`
- [ ] Cloudflare account (free) → Account ID + an API token with **Workers AI** permission → `.env`
- [ ] Kaggle: account, **phone verification** (needed for GPU and internet in kernels), Settings →
      API → Create token → `kaggle.json` at `C:\Users\echo\.kaggle\kaggle.json` (or env vars)
- [ ] GitHub: `gh auth login` (only needed by Step 6; doing it now avoids surprises)

### Tasks
1. **First commit, before any model call** (evidence that intent came first):
   - `git init`. `.gitignore` covers `.env`, `.venv/`, `__pycache__/`, `outputs/**/tmp/`,
     `outputs/.kaggle_staging/`, `*.log` and OS junk; it must **not** ignore `outputs/` itself.
   - `DESIGN.md` §1 Brief: audience (friends and family), where they watch (phones; WhatsApp,
     Telegram, social), intended feeling ("pride and warmth: they recognise him, and they see that
     his skills now live in me"), a How-Might-We statement, 2 personas (e.g. an aunt watching on
     WhatsApp with low sound; a cousin scrolling Instagram), constraints (deadline, free tiers, cartoon-only).
   - `DESIGN.md` §2 Ideation: the 4 storylines considered (A Toolbox, B Pass Me the…, C The House
     His Hands Built, D Let's Look at It First) and why A+D was chosen.
   - `ETHICS.md`: cartoon-only decision, the consent table (father: agreement pending/received),
     the privacy rule, the labelling plan, and a licence table with [VERIFY] markers.
   - Commit: `docs: audience, intent, ideation and ethics before any generation`.
2. **Python project:** `uv init --package`, pin Python 3.12 (`uv python pin 3.12`), add the
   dependencies:
   - runtime: `google-genai`, `httpx`, `jsonschema`, `python-dotenv`, `pyyaml`, `pillow`, `kaggle`, `rich`
   - dev: `pytest`
   - Run `uv lock`.
3. **`pipeline/common/`:**
   - `env.py`: loads `.env`; `require("CLOUDFLARE_API_TOKEN", why="keyframes stage")` raises a
     friendly message naming the stage and where to get the key.
   - `log.py`: `RunContext` (run_id, profile) and `log_event(...)`. A `timed_call()` context
     manager measures latency and writes the `model_call` line even on failure (`status:"error"`).
     Lines are appended atomically (open with `a` and write one line).
   - `cache.py`: `canonical_json`, `cache_key(...)`, `file_sha256`, and `Manifest` (load, get,
     put, is_fresh) with atomic writes (temp file + replace).
   - `retry.py`: `with_retry` decorator; `RetryableError`/`FatalError` classification for httpx
     and google-genai errors; reads `Retry-After`.
   - `storyboard.py`: `load_storyboard(path)`, `validate(sb)` (schema + §2.2 checks, returns a list
     of errors and warnings), and `timeline(sb, timing)` returning shot start, duration and narration offsets.
   - `ffmpeg.py`: `run(cmd, dry_run=False)` with stderr captured into the exception;
     `probe(path)` → duration/streams via ffprobe JSON.
4. **Providers:**
   - `base.py` Protocols with typed result dataclasses, e.g. `ImageResult(bytes, mime, width, height, seed, meta)`.
     - `TextProvider.generate_json(prompt, schema) -> dict`
     - `TTSProvider.synthesize(text, voice, style) -> AudioResult` (WAV bytes, sample_rate, duration)
     - `ImageProvider.generate(prompt, seed, w, h, refs=[], steps=None) -> ImageResult`
     - `VideoProvider` / `MusicProvider` are **batch-async**: `submit(jobs) -> handle`,
       `status(handle)`, `collect(handle) -> list[Result]`. Kaggle and most paid video APIs are async.
   - `registry.py`: `get_provider(stage, profile)` reads `config/providers.yaml` and builds the
     adapter plus its fallback chain.
   - `gemini_text.py`: google-genai `generate_content` with `response_mime_type="application/json"` and a JSON schema.
   - `gemini_tts.py`: `generate_content` with `response_modalities=["AUDIO"]` and a prebuilt voice
     name. The style goes in the prompt as a natural-language instruction ("Say warmly and
     unhurried: …"). It returns raw PCM **[VERIFY: 24 kHz, 16-bit mono]**, which is wrapped into a
     WAV with Python's `wave` module.
   - `cloudflare_image.py`: `POST https://api.cloudflare.com/client/v4/accounts/{id}/ai/run/{model}`.
     - FLUX.1 schnell: JSON body `{prompt, seed, steps≤8}` → base64 image in `result.image`.
     - FLUX.2 models: **[VERIFY]** multipart form-data with optional reference images
       (`input_image_0..3`), width and height.
   - `kenburns.py`: local FFmpeg zoompan "provider", so a Ken Burns clip looks like any other
     video result (`provider:"kenburns"`).
   - `paid_stubs.py`: classes that raise `NotImplementedError` with a pointer to docs/PAID_LANE.md.
5. **`config/providers.yaml`**: `free` profile filled in; `paid` profile written but pointing at
   the stubs. **[VERIFY]** the exact model ids in Step 0 by listing models: Gemini via
   `client.models.list()`, Cloudflare via the Workers AI models page/API. Record the ids found and
   any renames against the brief in FAILURES.md.
6. **`config/prices.yaml`**: keys for every model with `null` prices and a `source_url` field
   (filled in Step 6; nulls make COSTS.md show "unknown" rather than a wrong number).
7. **`pipeline/smoke.py`** (`make smoke`): one minimal call per provider using **neutral test
   prompts** ("a red apple on a table", "Testing one two three"). Each is written to `outputs/smoke/` and logged.
   - Gemini text: return `{"ok": true}` as JSON.
   - Gemini TTS: 1 sentence → WAV; probe the duration.
   - Cloudflare FLUX.1 schnell **and** FLUX.2 klein: 1 image each at 1024×1024 with a fixed seed,
     including a test of whether reference-image input works on klein. This result decides the
     consistency strategy in Step 3.
   - Kaggle: `kaggle kernels list --mine` or `kaggle datasets list --mine` to prove auth (no GPU spend).
   - A summary table at the end: provider, ok/fail, latency, notes.
8. **`pipeline/run.py`**: an argparse CLI with subcommands (the stage subcommands can be stubs now)
   and global flags `--profile`, `--force [shot…]`, `--dry-run`, `--only s05`.
9. **`Makefile`** targets: `setup` (uv sync + install pre-commit hook), `smoke`, `validate`, `test`,
   `check` (secrets + tests + validate), plus placeholders for all stage targets and `film`.
   `make help` lists them.
10. **`scripts/check_secrets.py`** and the `.git/hooks/pre-commit` installer.
11. **`tests/`**: `test_cache.py` (key stable across dict ordering; changing an irrelevant field
    keeps the key) and `test_log.py` (a line is valid JSON with the required fields).
12. Create stubs for `EXPERIMENTS.md`, `FAILURES.md` and `COSTS.md`, with templates from §13 at the top.

### Done when
- `make setup && make smoke` prints a table; every provider either succeeds (a line in `runs.jsonl`
  with latency) or has a FAILURES.md entry with the workaround.
- `make test` passes; `make check` finds no secrets.
- The free-tier limits actually observed (RPM/RPD for Gemini text and TTS, the Cloudflare daily
  neuron allowance, Kaggle weekly GPU hours shown in settings) are written into COSTS.md
  "Free tiers as found".

### Commits
`chore: scaffold uv project, Makefile, secrets hook` → `feat(common): logging, cache, retry, storyboard loader` →
`feat(providers): gemini text/tts, cloudflare flux, kenburns, registry, paid stubs` → `feat: smoke test (+ results in COSTS/FAILURES)`

### Risks and fallbacks
- A model name from the brief no longer exists → use the closest live successor, record it in FAILURES.md (the brief asks for this).
- FLUX.2 klein is missing on Workers AI or has no reference input → use FLUX.1 schnell with the
  text-only consistency strategy (fixed seed + identical character text). Record it.
- Kaggle phone verification is delayed → it does not block Steps 1–3; Kaggle is first needed in Step 4.

### Step 0 findings that change later steps (2026-11-25; details in FAILURES.md / COSTS.md)
- **Models (verified):** text `gemini-3.8-flash` → `gemini-3.5-flash-lite` (no 3.8 Flash-Lite text
  model; 3.8 Flash was 503 all afternoon). TTS `gemini-3.8-flash-tts` → `gemini-3.8-flash-lite-tts`
  via the **Interactions API**, not generate_content (style = a `speech_metadata` annotation; output
  is a complete 24 kHz mono 16-bit WAV). Image `@cf/black-forest-labs/flux-2-klein-4b` →
  `flux-1-schnell`.
- **Step 2 (critical): TTS free tier = 3 RPM, 10 requests/day per model** (Flash TTS and
  Flash-Lite TTS each; reset 11:00 EAT; failed requests count). Step 0 used 2 of each, so 8 + 8 are
  left today and 10 + 10 tomorrow. One request per line (~15 lines) + auditions (12) + Amharic takes
  (6) cannot fit. Plan for Step 2:
  - **Batch lines into a request**: put several lines in one request with clear pauses between
    them, then split the WAV at the silences (FFmpeg `silencedetect`) into per-line files, checking
    that segment count = line count. The first full pass = 1–3 requests per voice.
  - **Edits stay per line**: a changed line is re-synthesised alone (1 request), so "change one
    line → one model call" still holds for the walkthrough.
  - **Audition cheaply**: one request per candidate voice containing both test lines (3 requests);
    style vs no style on the chosen voice only (+1). Amharic: Dad's 3 lines in one request, 2 takes.
  - Keep Flash TTS for all final narration (one consistent voice); spend Flash-Lite TTS on auditions
    and experiments.
- **Step 3:** klein **reference images work** (plan A is on). The klein **seed does not reproduce**
  an image, and schnell accepts **no seed** at all → seeds pick candidates but don't guarantee
  re-creation; reproducibility = committed cached files. Budget ≈ 104 neurons per klein image
  (+22 per reference) out of 10,000/day (reset 03:00 EAT).
- **Step 4:** Kaggle GPU quota is **30 h, refreshing 28 Nov** (after the deadline). P100 is retired;
  choose the T4 with `--accelerator NvidiaTeslaT4` / `machine_shape`. The $10/$100 shown in Kaggle
  settings is the Model Proxy (AI inference) quota, not GPU time.
- **Smoke:** `make smoke` now also records `kaggle quota`; `make models` lists what the keys can see.

---

## 5. Step 1: Story, schema, storyboard

**Goal:** a validated `storyboard.json` with 10 shots, each with a reason, built from the draft in
§3 plus my real details.
**Time box:** ~1.5 h. **Inputs:** PLAN.md §2–3, DESIGN.md, my answers to the §3 questions **[ME]**.

### Tasks
1. Add to DESIGN.md: logline, a ~150-word treatment, the beat list (3–5 sentences, one picture per
   beat), the visual approach (cartoon style block, palette, why cartoon) and the sound approach
   (narration-led; quiet score, theme returns).
2. Write `schema/storyboard.schema.json` (Draft 2020-12) to match §2.1. Use `additionalProperties:
   false` on the main objects so typos are caught; enums for `shot_size`, `camera`, `motion`,
   `kenburns.move` and `transition_in`; numeric ranges (seeds ≥ 0, durations > 0, 8 ≤ shots ≤ 12).
3. `pipeline/script.py` (the brief's "script" stage):
   - Reads DESIGN.md (treatment) + the schema and asks Gemini Flash to draft a storyboard as
     structured JSON, writing to `storyboard.draft.json`. **It never overwrites `storyboard.json`.**
   - The draft is compared with the hand-written §3 version, and the best parts are merged by hand.
   - This gives the report a concrete "AI draft vs human edit" comparison → EXPERIMENTS.md E01.
   - Logged like any model call.
4. Write `storyboard.json`:
   - character descriptions (from my answers; one fixed sentence each, about 25–40 words)
   - the style block and negative prompt
   - shots s01–s10 with image prompts (subject + setting + shot size + composition "subject centred, room above and below")
   - motion prompts (one gentle movement + camera, e.g. "the man slowly slides out from under the car, camera static")
   - Ken Burns moves (varied: push_in, pan_left, pull_out, pan_right…)
   - priorities (the most emotional shots first: s09, s10, s05, s03, s08, s02…)
   - music cue, voices, end card
5. `make validate` → fix until clean. Add `tests/test_schema.py`: the real storyboard validates; 5
   deliberately broken fixtures (duplicate id, unknown character, missing reason, bad enum, too few
   shots) fail with the expected message.
6. Add DESIGN.md §"Shot reasons" (or point to the `reason` fields) so every shot has a reason a reviewer can read.

### Done when
`make validate` passes with zero errors, every shot has a reason, and `make test` passes.

### Commits
`feat(schema): storyboard JSON Schema + semantic checks` → `feat(script): Gemini storyboard draft stage` → `story: storyboard v1 (10 shots)`

### Risks
- Narration too long or short → it gets measured in Step 2; don't fine-tune word counts by hand here.

---

## 6. Step 2: Narration and the radio cut (Phase 1 checkpoint)

**Goal:** real narration timing drives shot lengths; a radio cut goes in front of 3+ people.
**Time box:** ~1.5 h of build. The user test runs asynchronously while Step 3 starts.

### Tasks
1. `pipeline/narration.py` (`make narration`):
   - For each shot and each narration line: build the TTS input (style instruction + text) and a
     cache key (text, voice, style, model). On a cache miss, synthesize → `outputs/narration/<shot>/<key>.wav`.
   - Trim leading and trailing silence (FFmpeg `silenceremove` with conservative thresholds) and
     store both the raw and the trimmed file. Measure the duration (ffprobe).
   - Write `outputs/narration/timing.json`: `{shot_id: [{line_idx, voice, path, duration_s, words, wps}]}`
     plus totals (words, seconds, words per second).
   - Respect the free-tier rate limit with a client-side limiter. **[VERIFY]** the RPM found in
     Step 0; default to 1 call every ~6 s to be safe.
2. **Voice audition** (EXPERIMENTS.md E02/E03): the same 2 lines (s01 and s10) in 3 stock voices,
   with and without a style instruction. I pick by ear **[ME]**, and the choice is recorded with
   reasons. Then pick a different, deeper stock voice for Dad (E04).
2b. **Amharic lines** (EXPERIMENTS.md E18): send Dad's 3 lines in Ge'ez script with a style
   instruction ("Speak in Amharic, calm, warm, a father talking to his son").
   - Generate 2 takes each and check them by ear **[ME, native speaker]**: pronunciation, stress,
     and whether the voice stays the same character across lines.
   - If a line is poor, try the `tts_text` transliteration (*Eski, enyew*). If it is still poor,
     use the English fallback in the same voice.
   - Record exactly where it failed in FAILURES.md. This is evidence of language support that the brief explicitly values.
3. After timing exists, `validate` runs the hard 60–90 s check. If the film is too long or short,
   trim or extend the narration text and re-run; only the changed lines regenerate.
4. **Placeholder music** (`pipeline/music.py --placeholder`): a code-generated soft pad (FFmpeg
   `aevalsrc` with a few low sine partials, slow tremolo, gentle fades) for the film's length. It
   needs no licence and is clearly labelled as a placeholder.
5. `pipeline/assemble.py --mode radio` (`make radio`):
   - Timeline from `storyboard.timeline()`: shot start/duration; narration placed at start + `pad_before`.
   - Narration stem: `adelay` per line + `amix` (normalize=0) → `outputs/cuts/narration_stem.wav`.
   - Mix: placeholder music ducked with `sidechaincompress` (values from `storyboard.music.duck`),
     then mixed with the narration, then two-pass `loudnorm` to I=−14, TP=−1, LRA=11.
   - Video: black `color` source at 1280×720 24 fps, plus burned-in subtitles (from the subtitle
     builder, which Step 5 reuses).
   - Output: `outputs/cuts/radio_cut.mp4` (H.264/AAC, faststart) and `outputs/cuts/radio_cut.srt`.
6. **Subtitle builder** (`common/subtitles.py`, shared with Step 5): split each line into cues of
   ≤ 2 lines × ≤ 40 characters, breaking at punctuation and then at spaces. Cue times are
   proportional to character count within the line's measured audio span; minimum cue 1.0 s.
   Lines with a `subtitle` override use that text (Dad's Amharic → the English translation, in
   italics). Write SRT. Add `tests/test_subtitles.py`.
7. **User test 1 [ME]:** send the radio cut to ≥ 3 friends or family (WhatsApp is fine) with these questions:
   1. In one sentence, what is this film about?
   2. Which moment stayed with you?
   3. Was anything confusing, too slow or too fast?
   4. How did you feel at the end?
   5. Did anything sound wrong (a word, a name, a pause)? Did Dad's Amharic lines sound natural?
   6. Does this feel like *our* family and home? What detail is missing or wrong?

   Paste their answers back verbatim. Identify people by relationship or initials, not full names.
8. **Process test 1:** add DESIGN.md §"User test 1": date, format, who (relationship), verbatim
   notes, where they reacted, insights, **changes decided**. Apply the changes to `storyboard.json`
   in a dedicated commit that references the test, so the change is visible in git history. Re-run
   `make narration radio`; only the changed lines regenerate, which the logs show.

### Done when
`radio_cut.mp4` plays end to end at 60–90 s, `timing.json` exists, DESIGN.md records test 1, and
the storyboard commit shows the changes made because of it.

### Commits
`feat(narration): gemini tts per line, cached, timing.json` → `feat(assemble): radio cut + subtitles + ducking + loudnorm` →
`docs(design): user test 1 notes` → `story: apply user test 1 changes (…)`

### Risks
- TTS daily quota runs out → caching means each line is paid for only once. Batch the edits and regenerate once.
- Pronunciation of names or unusual words → re-spell phonetically in the TTS text only, keeping the
  subtitle text correct (`narration[].tts_text` optional override). Record it in FAILURES.md.

---

## 7. Step 3: Reference sheets and keyframes

**Goal:** the cartoon look and characters are locked; there is a keyframe for every shot; a
complete Ken Burns "stills film" exists from here on.
**Time box:** ~3 h. **Inputs:** storyboard, the Step 0 result on reference support.
**Budget:** the Cloudflare daily allowance (roughly 50–170 images per the brief **[VERIFY]**; it
resets at 00:00 UTC = 03:00 EAT). Plan ≈ 24 reference images (style + 5 characters × 4) + 33 keyframes (10 shots + the second s10 layer, × 3) + ~15 experiment images; split across two daily allowances if needed.

### Tasks
1. `pipeline/keyframes.py refs` (`make refs`):
   - **Style reference:** 4 candidates of a neutral scene (the toolbox on a table) using the style
     block → I pick one → `style.reference_choice`. **[ME]**
   - **Character sheets:** for each of dad, me_child, me_teen and me_adult, 4 candidates of a
     full-body figure, front view, plain light background, neutral pose, the character description
     + style block, fixed seed per candidate (seed, seed+1…). If klein supports references, the
     style reference is passed in. I pick one each → `characters[].reference_choice`. **[ME]**
   - **Age chain:** me_teen and me_adult are generated *with the chosen me_child sheet as a
     reference* ("the same boy, older"), and dad_now *from the chosen dad sheet* ("the same man,
     ten years older, more grey"), if klein supports references. This keeps faces related across
     ages. Fallback: text-only + colour anchors (E19).
   - Check the Habesha features and skin tones on every candidate: no drift toward generic or
     lighter-skinned defaults, no stereotyped rendering. A rejected candidate goes in EXPERIMENTS.md with the reason.
   - Optionally a turnaround sheet (front, side, three-quarter) for Dad only, if time allows.
   - Contact sheets (`outputs/refs/contact_<character>.png`, made with Pillow) show the candidates
     side by side, labelled with seeds. Choosing is easier, and the choice can be described in text.
2. **Consistency strategy:**
   - **A (preferred, if supported):** FLUX.2 klein with reference images: the character ref(s) for
     the shot + the style ref (max 4 refs **[VERIFY]**), plus the full text prompt.
   - **B (fallback):** FLUX.1 schnell, text-only: identical character sentences + style block, and
     a fixed per-character seed offset.
   - EXPERIMENTS.md E05 runs A vs B on the same 2 shots with the same seed, comparing consistency
     (my judgement + 2 people), latency and allowance used.
3. `pipeline/keyframes.py shots` (`make keyframes`):
   - For each shot, generate 3 candidates (seeds `shot.seed`, +1, +2) at 1024×1024, composition
     "subject centred, important action inside the central 56% width band". The central band is
     what survives both crops.
   - Make a contact sheet per shot, plus **crop previews** (the 9:16 and 16:9 crops overlaid as
     rectangles) to check both aspect ratios before animating.
   - **[ME]** I pick one per shot → `keyframe_choice`. Check faces and hands; regenerate (max 3
     creative attempts) or adjust `crop_focus`.
   - Cache: a changed prompt, seed, style or reference regenerates only that shot's candidates.
4. `pipeline/shots.py kenburns` (`make kenburns`):
   - For each shot, render the chosen keyframe into a 1024×1024 24 fps master clip of the shot's
     computed duration with zoompan. Upscale first (`scale=4096:-1`) to avoid zoompan jitter; ease
     with a cosine curve; the `move` and `amount` come from the storyboard.
   - Write to `outputs/kenburns/<shot>/<key>.mp4`, logged as a `kenburns` provider call (latency, no cost).
5. `assemble.py --mode rough`: the radio-cut audio + Ken Burns pictures in both aspect ratios →
   `outputs/cuts/rough_kb_9x16.mp4`, `rough_kb_16x9.mp4`. **This is the safety-net film**; from
   here on there is always something to submit.
6. EXPERIMENTS.md entries as they happen: E05 (refs vs text-only), E06 (style block wording, e.g.
   "hand-painted gouache" vs "flat vector cartoon"), E07 (klein steps or schnell steps vs latency
   and quality), E08 (centred composition instruction vs none → crop survival).

### Done when
Every shot has a chosen keyframe in which the main character is recognisably the same person
across shots (judged by me + 1 person, noted in EXPERIMENTS.md), and the rough Ken Burns film
exists in both aspect ratios.

### Commits
`feat(keyframes): reference sheets + contact sheets` → `refs: choose style + character refs (why)` →
`feat(keyframes): per-shot keyframes with crop previews` → `feat(shots): ken burns fallback clips` → `cut: rough ken burns film`

### Risks
- Identity drift (most likely on Dad's face) → lean on hands and objects; simplify prompts; use
  medium and wide shots for Dad; keep the same clothing colours (the strongest cue in cartoons).
  Log what worked.
- The daily allowance runs out → finish the remaining keyframes after 03:00 EAT, or fall back to
  FLUX.1 schnell for the remaining shots (log it).

---

## 8. Step 4: Moving shots (Wan 2.2) and music (ACE-Step) on Kaggle

**Goal:** animated clips for as many shots as GPU time allows, in priority order; 3 score
candidates and a written choice.
**Time box:** ~2.5 h to build and push tonight; jobs run overnight; ~1 h tomorrow morning to pull and review.

### 8.1 Shared Kaggle mechanics (`pipeline/providers/kaggle_common.py`)
- **Inputs go in a private Kaggle dataset** per stage: `<user>/toolbox-wan-jobs`,
  `<user>/toolbox-music-jobs`.
  - Staging dir: `outputs/.kaggle_staging/<stage>/` holds `jobs.json`, the input images and `dataset-metadata.json`.
  - First time: `kaggle datasets create -p <dir>`; afterwards: `kaggle datasets version -p <dir> -m "<jobs hash>"`.
  - Poll `kaggle datasets status` until it is ready.
- **The kernel is a script kernel** (`kernel_type: "script"`, `language: "python"`,
  `is_private: true`, `enable_gpu: true`, `enable_internet: true`, `dataset_sources: [...]`).
  **[VERIFY]** how the CLI selects the accelerator (T4×2 vs P100); record what is used.
- **Wrong-dataset-version guard:** at push time the job hash is templated into the kernel file
  (`EXPECTED_JOBS_SHA = "…"`). The kernel checks it against `jobs.json` and exits with a clear
  error if they differ. This prevents running on a stale dataset version.
- **The kernel writes results incrementally** to `/kaggle/working/`:
  - the outputs themselves
  - `results.jsonl` (job_id, ok, seconds, gpu_name, peak_vram_gb, params, error)
  - `env.json` (torch/diffusers versions, GPU, CUDA)

  If the session dies, everything finished so far is still downloadable.
- **A time budget inside the kernel:** stop starting new jobs once there is not enough time left
  for one more. The session limit is ~12 h **[VERIFY]**; budget 8 h.
- **Local CLI:**
  - `shots.py push` → computes stale shots → builds jobs → versions the dataset → `kaggle kernels push -p pipeline/kaggle/wan_kernel`
  - `shots.py wait` → polls `kaggle kernels status <user>/toolbox-wan` every 2 min
  - `shots.py pull` → `kaggle kernels output <user>/toolbox-wan -p outputs/.kaggle_staging/wan_out`
    → ingests `results.jsonl` → copies clips into `outputs/shots/<shot>/<cache_key>.mp4`, updates
    the manifest, appends `model_call` lines (latency = measured seconds, `gpu_s` = seconds × GPUs used)
  - `make shots` = push + wait + pull; `make shots-push`, `make shots-pull` run separately for overnight runs.
- Push and pull are logged as `external_job` events (kernel version, status, wall time).

### 8.2 Wan 2.2 kernel (`pipeline/kaggle/wan_kernel/wan_job.py`)
- **Install:** pinned `diffusers`, `transformers`, `accelerate`, `ftfy` and `imageio[ffmpeg]`
  (exact versions recorded in `env.json`). **[VERIFY]** which diffusers pipeline class supports
  Wan2.2 TI2V-5B image-to-video, and the repo id (`Wan-AI/Wan2.2-TI2V-5B-Diffusers`).
- **Weights:** `huggingface_hub.snapshot_download` with only the needed files, into `/kaggle/tmp`
  or another large-disk path (not `/kaggle/working`, which has a 20 GB output limit). Check
  whether Wan is mirrored on Kaggle Models; if so, attach it as `model_sources` to skip the download.
- **Memory plan for a T4 (16 GB, no bf16):**
  1. Phase A: load the text encoder, encode all prompts and the negative prompt, cache the
     embeddings, then free the encoder.
  2. Phase B: load the transformer + VAE in fp16. If 2 GPUs are available, run one worker per GPU
     on interleaved jobs; else one worker.
  3. Fallback: `enable_model_cpu_offload()` and VAE tiling or slicing.
  4. Watch the 29 GB system RAM limit.
- **Params (drafts; finals only if time allows):** 704×704 (multiples of 32), 81 frames
  (~3.4 s @ 24 fps), ~30 steps, guidance ≈ 5, the seed from the storyboard. The negative prompt
  comes from the style block plus motion artifacts ("flicker, morphing, warping, extra limbs").
  - The prompt is the motion prompt + a short style suffix ("hand-painted cartoon, gentle motion").
  - EXPERIMENTS.md: E09 (resolution vs minutes per clip), E10 (frames 49 vs 81), E11 (simple
    motion prompt vs the full formula), E12 (steps 20 vs 30).
- **Per-job safety:** catch CUDA OOM → empty the cache → retry once with fewer frames (49) and a
  lower resolution (576×576) → else record the failure and continue. Never let one shot kill the batch.
- **Order:** jobs sorted by `priority`. A **pilot job first** (1 shot, 49 frames) measures
  minutes/clip and writes it to results immediately, so the first pull can decide whether the full batch is realistic.
- **Expected cost [VERIFY by pilot]:** tens of minutes per clip on a T4. 10 clips may take 5–8 GPU
  hours, within the ~30 h/week quota. If too slow, animate only priority 1–5 and use Ken Burns for the rest.

### 8.3 ACE-Step 1.5 kernel (`pipeline/kaggle/acestep_kernel/acestep_job.py`)
- Install per the ACE-Step 1.5 repo README **[VERIFY]** the API/CLI and its parameter names:
  caption, lyrics (`[instrumental]`), duration, bpm, key, seed, batch size.
- Jobs: cue "main", duration = film length (from the timeline) + 4 s tail, 3 candidates
  (seeds 301/302/303, same caption). Optionally a 4th with a caption variant (E13).
- Caption draft: "gentle nostalgic acoustic instrumental, warm fingerpicked guitar, soft plucked
  lyre, light hand percussion, airy pad, intimate home feeling, no lead melody, sparse, space for
  narration". BPM and key go in metadata fields, not the caption (Appendix B).
- If a full-length track is unstable (> 60 s), generate 2 sections (memories / the turn + ending)
  and crossfade them in assembly → FAILURES.md if needed.
- Run this kernel **first** (it is quick), then the Wan kernel.

### 8.4 Audition and choice
- `music.py audition` renders 3 versions of the radio cut, one per candidate, ducked under the
  narration at normal level → `outputs/cuts/audition_c1..c3.mp4`.
- **[ME]** I listen at low volume, under the narration, on a phone speaker and on headphones. I pick
  one and say why (texture, whether it fights the voice, the ending lift) → `music.chosen.main`
  + EXPERIMENTS.md E13/E14.
- The music stage also measures LUFS per candidate (`ebur128`) for the record.

### 8.5 Rough cut checkpoint
`assemble.py --mode rough` picks, per shot, a **fresh** Wan clip if present, else Ken Burns, plus
the chosen score → `outputs/cuts/rough_9x16.mp4`, `rough_16x9.mp4`.

### Done when
The music choice is recorded; every `motion:"wan"` shot either has a clip or a FAILURES.md entry
explaining why it is Ken Burns; GPU minutes per clip are in runs.jsonl; the rough cut exists.

### Commits
`feat(kaggle): dataset+kernel push/poll/pull with hash guard` → `feat(music): acestep kernel + audition` →
`feat(shots): wan 2.2 kernel` → `music: choose candidate cN (why)` → `shots: ingest wan clips (N/10)`

### Risks
- OOM, a slow T4 or a P100 instead of a T4 → follow the fallback ladder in §8.2. Every rung goes in FAILURES.md (this is graded evidence).
- Kernel internet blocked (phone not verified) → fix the verification. Meanwhile the Ken Burns film stands.
- Quota exhausted → stop; Ken Burns covers the remaining shots. Note the GPU hours used in COSTS.md.

---

## 9. Step 5: Assembly, both exports (Phase 3 edit)

**Goal:** the final 60–90 s film in 9:16 and 16:9, built entirely from code and the storyboard;
`make film` works from a clean clone.
**Time box:** ~3 h (tomorrow by ~13:00).

### Tasks (`pipeline/assemble.py --mode final`)
1. **Timeline:** `storyboard.timeline()` with real narration durations → per-shot start and
   duration; the end card is appended.
2. **Per-shot segments** (cached by a key of inputs + params; FFmpeg is deterministic):
   - Source: a fresh Wan clip (trim the weak first and last ~0.25–0.5 s) or a Ken Burns clip.
   - If the clip is shorter than the shot: **hold and drift**. Freeze the last frame and continue
     with a slow zoompan for the remainder, so the hold doesn't feel dead. EXPERIMENTS.md E15
     compares this with slow-motion (`setpts`).
   - Crop the square master by aspect using `crop_focus` (9:16 → a 576×1024 crop region; 16:9 →
     1024×576), scale with Lanczos to 720×1280 or 1280×720, 24 fps CFR, `setsar=1`, `yuv420p`.
   - **s10 split screen** (`layers`): each layer is cropped to a half-frame (9:16 → two 720×640
     halves `vstack`ed; 16:9 → two 640×720 halves `hstack`ed), with a thin divider in a palette
     colour. Fallback: layer `a` alone, full-frame.
3. **Transitions:** default hard cut; `dissolve` = `xfade` 0.5 s; `fade_from_black` on s01; fade
   to black before the end card. xfade offsets are computed from the timeline, which uses the same
   math the subtitles use.
4. **End card** (`common/endcard.py`):
   - Pillow renders a 720×1280 and a 1280×720 PNG: "Made with AI" (large), the credits and model
     list from `storyboard.end_card.lines`, using a calm colour from the style palette.
   - The font is an OFL font in `assets/fonts/` (e.g. Atkinson Hyperlegible or Nunito, with its
     licence file).
   - Shown for 3 s, with the music tail fading out under it.
5. **Audio:**
   1. Narration stem (as in Step 2), pre-normalised (single-pass loudnorm to about −16 LUFS). It
      includes Dad's lines and the s09 echo (`aecho` + gain from the `echo_of` line, with no new TTS call).
   2. Music: the chosen candidate, trimmed to film length + end card, 1 s fade-in, 3 s fade-out,
      pre-normalised to about −20 LUFS. Bringing sources to similar levels first makes the balance
      a creative choice (Appendix B).
   3. Duck the music with `sidechaincompress` (sidechain = narration; params from the storyboard;
      tune by ear → E16).
   4. Mix narration + ducked music → two-pass `loudnorm` I=−14, TP=−1, LRA=11 (linear mode on the
      second pass) → 48 kHz stereo.
6. **Subtitles:** the Step 2 builder on final timings → `outputs/final/film.srt`, burned in with
   libass.
   - The 9:16 style is larger and placed higher (MarginV about 22% of the height, inside the
     platform safe area); the 16:9 style sits near the bottom.
   - `fontsdir=assets/fonts`, an outline and a soft shadow for readability over bright frames.
7. **Encode:** libx264 `-crf 18 -preset slow -pix_fmt yuv420p -r 24`, AAC 192 kbps 48 kHz,
   `-movflags +faststart`, plus MP4 metadata `comment="Made with AI — see end card"`. Never strip
   provenance metadata or watermarks from any source.
   → `outputs/final/the_toolbox_9x16.mp4`, `the_toolbox_16x9.mp4`.
8. **QC** (`outputs/final/qc.json`, the run fails if out of tolerance):
   - ffprobe: duration 60–90 s, 24 fps, both streams present, the right resolution
   - an `ebur128` measurement of the final: integrated −14 ± 1 LUFS, true peak ≤ −1 dBTP
   - the subtitle count matches the narration lines
9. **`make film`:** validate → narration → keyframes → kenburns → shots (**pull/ingest only by
   default**; `RUN_GPU=1` pushes stale Wan jobs) → music (cached) → assemble final → qc → costs.
   - A clean clone with the committed `outputs/` gives all cache hits plus reassembly, so a stranger
     can run it with no keys.
   - If a key is missing **and** something is stale, the run stops with a message naming the stage,
     the shot and the key needed.
10. **Clean-clone test:** `git clone . ../toolbox-clean && cd ../toolbox-clean && make setup film` →
    must succeed; the output is compared via the hashes in qc.json. Record the result in README/ARCHITECTURE.
11. Tests: `test_timeline.py` (offsets, holds, end card), `test_ffmpeg_cmds.py` (filter strings for
    ducking, loudnorm and crops are built correctly in dry-run mode).
12. **User test 2 [ME]:** send the near-final 9:16 cut to ≥ 3 people (ideally at least 1 who saw
    the radio cut). The same questions, plus: "Did the characters feel like the same people
    throughout?" and "Could you read the subtitles?". Record it in DESIGN.md §"User test 2". Apply
    the changes in a referenced commit; re-run `make film` (only the affected shots regenerate).

### Done when
Both MP4s pass QC, test 2 is recorded with its changes applied, and the clean clone reproduces the film with one command.

### Commits
`feat(assemble): final edit, ducking, loudnorm, subtitles, end card, 2 aspects` → `test: timeline + ffmpeg builders` →
`docs(design): user test 2` → `story: apply user test 2 changes (…)` → `film: final v1`

---

## 10. The paid alternative (future lane, designed in now)

### 10.1 How it plugs in
- Every stage calls `get_provider(stage, profile)`. `make film PROFILE=paid` (or `--profile paid`)
  switches adapters. **`storyboard.json` does not change.**
- Provider and model are part of every cache key, so switching profiles regenerates only the
  stages whose provider changed, and both versions sit side by side in `outputs/` for comparison.
- In Step 0, `paid_stubs.py` defines the classes with the right Protocol signatures; each raises
  `NotImplementedError("see docs/PAID_LANE.md")`. Implementing one later is a single file plus a
  config line.
- `docs/PAID_LANE.md` (written in Step 6) covers per-stage options, what paying buys, the
  integration notes for each, the migration checklist and the benchmark protocol below.

### 10.2 Options per stage

| Stage | Free (now) | Paid candidates (future) | What paying buys | Integration note |
|---|---|---|---|---|
| Script / storyboard | Gemini Flash (free tier) | Gemini paid tier; Claude (Sonnet/Opus) | Higher limits; data not used for training | Sync `TextProvider`; same JSON-schema call |
| Narration | Gemini Flash TTS | Gemini TTS paid tier; ElevenLabs | Rate limits; finer voice/prosody control | Sync `TTSProvider`; WAV out |
| Keyframes | FLUX.2 klein / FLUX.1 schnell (Cloudflare) | Nano Banana (Gemini image); FLUX.2 pro/flex via BFL API or fal.ai | Much stronger multi-reference character consistency; image editing | Sync `ImageProvider` with `refs` |
| Moving shots | Wan 2.2 TI2V-5B on a Kaggle T4 | Gemini Omni Flash video; Wan 2.2 A14B, Kling etc. via fal.ai or Replicate; **the same Wan code on a rented GPU** (RunPod / Modal, L40S or A100/H100) | 720p–1080p, no T4 queue, minutes instead of hours | Async `VideoProvider` (submit/poll/collect), the same shape as Kaggle |
| Music | ACE-Step 1.5 on Kaggle | Lyria 3.5; ACE-Step on a rented GPU | Higher fidelity; longer coherent cues | Async `MusicProvider` |
| Assembly | FFmpeg (local) | Unchanged | — | — |

### 10.3 Rules for the paid lane
- **Prices change often:** read the list prices from each provider's pricing page at the time of
  use and write them, with the URL and date, into `config/prices.yaml`. The same file feeds the
  COSTS.md "list-price equivalent" column now (Kaggle GPU time is priced at a public on-demand
  rate for a comparable GPU).
- The cheapest "paid" upgrade is often **the same open models on a rented GPU**. The kernel code is
  plain Python scripts with a `main(jobs_path, out_dir)` entry point, not notebook-only logic, so
  it runs unchanged on RunPod or Modal.
- Before adopting a provider, check its licence and output terms, whether outputs carry watermarks
  or provenance (SynthID, C2PA), and its data-retention policy. Keep provenance intact. Update ETHICS.md.
- Set budget guards in config (`max_usd_per_run`, `max_calls_per_stage`). The run stops before exceeding them.
- If the cohort's organisation key arrives (Omni Flash, Nano Banana, Lyria 3.5), use it for the
  benchmark below (ceiling work).

### 10.4 Benchmark protocol (ceiling work, if time or a key allows)
- Pick the same shot (s09 or s10), with the same keyframe and the same motion prompt.
- Generate it with the open model (Wan on a Kaggle T4) and a frontier/paid model. Log cost, latency and resolution.
- Run a **blind preference test with ≥ 5 people**: show A and B in random order, ask which they
  prefer and why, then record the votes and quotes.
- Write it up in EXPERIMENTS.md + the report: cost per second of video, latency, preference, and
  whether the difference matters for *this* audience.

---

## 11. Step 6: Docs, measurement, release, report

**Goal:** a repository a stranger can follow and reproduce; all graded documents complete and
backed by logs; the films and post live.
**Time box:** ~5 h (tomorrow afternoon/evening).

### Tasks
1. **`pipeline/costs.py`** (`make costs`) generates the tables in **COSTS.md** from `runs.jsonl`:
   - Per stage: model calls, cache hits, failures, retries, total and mean latency, GPU minutes,
     cost (USD; 0 on the free lane), list-price equivalent from `prices.yaml`.
   - Per model: the same breakdown.
   - The whole film: total wall time and GPU minutes, and the list-price equivalent.
   - A manual section: free tiers as found (with dates), quota events, and the frontier comparison if done.
2. **README.md:**
   - what this is (with a one-line story)
   - quickstart: prerequisites (uv, FFmpeg, make), `cp .env.example .env` (optional if outputs are
     committed), `make setup`, `make film`
   - how to change one shot (edit s05 narration → `make film` → only s05 TTS regenerates: an example `runs.jsonl` excerpt)
   - the GPU stage (`RUN_GPU=1`, Kaggle setup), the stage targets, the repo layout, the cost
     summary (from COSTS.md), links to the docs, licences, the AI labelling note
3. **ARCHITECTURE.md:**
   - a Mermaid stage diagram
   - the contract (schema + manifests); per-stage inputs/outputs table; the cache-key definition
     with a worked example; staleness rules
   - failure handling (retries, fallback chains, the Kaggle hash guard, OOM ladder, QC gates)
   - provider profiles and the paid lane; logging format; determinism notes (seeds, FFmpeg)
   - known limitations
4. **EXPERIMENTS.md:** at least 12 entries in the template (planned backlog below), each tied to
   evidence (run_ids, cache keys, file paths, measured numbers).
5. **FAILURES.md:** complete. Every real blocker hit: quota, memory, consistency, model renames,
   Windows quirks, TTS pronunciation.
6. **ETHICS.md:** final consent table with dates; the licence of **every** model, output, font and
   tool actually used (verified); the labelling plan with the platform toggles used; the privacy
   measures.
7. **Clean-clone test** again, then: `gh repo create <name> --public --source . --push`, after
   confirming with me. **[ME]**
   - Check the repository size (no file > 50 MB; total comfortably < 1 GB).
   - Optionally a GitHub Release with both MP4s attached, which gives direct links that open
     without login for Assignment 2.
8. **`docs/REPORT_DRAFT.md`** → I rewrite it in my own voice and export it to PDF/DOCX **[ME]**.
   Sections required by the brief:
   1. what I set out to make, and for whom
   2. what I learned from my audience (tests 1 and 2, quotes, the changes)
   3. the hardest problem and how I solved it (with links to FAILURES/EXPERIMENTS entries)
   4. a suggested practice that beat my instinct, with evidence
   5. a suggested practice that did not, with evidence
   6. ceiling work and what it taught me
   7. what I would build next (the paid lane, a family web app…)
9. **`docs/WALKTHROUGH_SCRIPT.md`** (≤ 5 min) → I record it **[ME]**:
   - 0:00–0:20: a 15 s clip of the film
   - 0:20–1:30: the architecture (diagram, storyboard as contract, stages, cache, logs)
   - 1:30–2:30: one hard decision (e.g. square masters for two aspect ratios, or Kaggle automation
     with the hash guard, or the consistency strategy)
   - 2:30–4:30: **live:** edit one narration line in `storyboard.json` → `make film` →
     `tail runs.jsonl` shows exactly one new `model_call` (TTS, s0N) and the rest `cache_hit` →
     play the changed shot
   - 4:30–5:00: one thing learned
10. **`docs/POST_DRAFT_NOTES.md`:** bullet prompts only (story, why it matters, one learning). **I
    write the post myself [ME]**, the brief requires it. Platform AI labels: YouTube "altered or
    synthetic content", TikTok "AI-generated content", Meta "AI info" **[VERIFY]** the current
    toggle names. Switch the label on even though it's a cartoon.

### Done when
The submission checklist (§14) is all ticked.

### Commits
`feat(costs): COSTS.md generated from runs.jsonl` → `docs: README, ARCHITECTURE, ETHICS final` →
`docs: experiments + failures complete` → `docs: report draft, walkthrough script, paid lane` → `release: v1.0`

---

## 12. Ceiling (only after Steps 0–5 are done; pick at most one)
1. **Open vs frontier benchmark** (§10.4). Strongest if an organisation key arrives.
2. **A tool for others:** `pipeline` as a CLI (`toolbox-film new|validate|film`) with a template storyboard.
3. **Measure the audience** after posting: views, shares, comments over 24 h, and what got shared.
4. **A second language** (e.g. Amharic narration via Gemini TTS, documenting where it fails).

Judged on insight, not volume: one well-measured experiment that changed my mind is worth more than features.

---

## 13. Templates, backlog and risk register

### EXPERIMENTS.md entry template
```
## E07 — <short title>
- Date / run_id(s):
- Hypothesis: If I <change>, then <expected effect> because <reason>.
- Change (one variable): …        Held fixed: seed=…, prompt=…, model=…
- Result (measured): latency …, calls …, observation …, who judged …
- Decision: keep / revert / follow-up E0x
- Evidence: runs.jsonl lines (run_id …), files outputs/…/<key>.png
```

### FAILURES.md entry template
```
## F03 — <stage>: <symptom in a few words>
- When / run_id:
- Symptom (exact error text):
- Cause (verified or suspected):
- Tried: 1) … 2) …
- Resolution / workaround:
- Time lost:  Lesson:
```

### Experiment backlog (aim for ≥ 12 real entries)
| ID | Stage | Question |
|---|---|---|
| E01 | script | Gemini-drafted storyboard vs my hand-written draft: what did each get right? |
| E02 | tts | 3 stock voices on the same 2 lines: which fits the narrator? |
| E03 | tts | Style instruction vs none: effect on pacing (measured words/s) and warmth |
| E04 | tts | A separate Dad voice for "Let's look at it first": does it land better? (user test) |
| E05 | image | Reference conditioning (klein) vs text-only fixed seed (schnell): consistency, latency |
| E06 | image | Style-block wording A vs B: cohesion across shots |
| E07 | image | Steps vs quality vs latency |
| E08 | image | "Subject centred" composition: crop survival for 9:16 and 16:9 |
| E09 | video | Wan resolution (576 vs 704): minutes per clip vs quality |
| E10 | video | Wan frames 49 vs 81: motion quality vs time |
| E11 | video | Motion-only prompt vs the full Wan formula |
| E12 | video | Wan clip vs Ken Burns for the same shot: which does the audience prefer? |
| E13 | music | 3 ACE-Step seeds (same caption): choose + why |
| E14 | music | Caption with vs without "no lead melody": does it fight the voice? |
| E15 | edit | Hold-and-drift vs slow motion to stretch short clips |
| E16 | mix | Ducking release 1500 ms vs 800 ms: pumping vs intelligibility |
| E17 | edit | 9:16 crop vs blurred-background pad for the vertical export |
| E18 | tts | Amharic in Ge'ez script vs transliteration vs English fallback for Dad's lines: pronunciation as judged by a native speaker |
| E19 | image | Age chain: teen/adult generated from the child reference vs text-only: do they read as the same person? |

### Risk register
| Risk | Likelihood | Impact | Mitigation / fallback |
|---|---|---|---|
| Wan too slow or OOM on a T4 | High | Medium | Pilot job first; priority order; OOM ladder; Ken Burns for the rest (still a valid film) |
| Character identity drift | Medium | High | Lock refs first; same description text; same clothing colours; hands and objects shots; medium/wide for faces |
| Free-tier quota exhausted (TTS, Cloudflare) | Medium | Medium | Caching; batch edits; Cloudflare reset at 03:00 EAT; schnell fallback |
| Model renamed or retired vs the brief | Medium | Low | Verify in Step 0; successor model; FAILURES.md entry |
| Kaggle phone verification or internet blocked | Low–Med | Medium | Do it now; Ken Burns film unaffected |
| User tests can't happen in time | Medium | High (graded) | Send the radio cut as soon as it exists; async on WhatsApp; ≥ 3 people each time |
| Running out of time tomorrow | Medium | High | The safety-net Ken Burns film exists from Step 3; docs-as-you-go; cut ceiling work first |
| Secrets committed | Low | High | Pre-commit secret scan; `.env` gitignored; check before push |
| Repo too big for GitHub | Low | Medium | 720p finals, small drafts, no file > 50 MB; prune old candidate versions if needed |

---

## 14. Things only I can do **[ME]**: checklist
- [ ] Gemini key · Cloudflare account ID + token · Kaggle phone verification + `kaggle.json` · `gh auth login`
- [ ] Father's agreement to the story (message; date it in ETHICS.md)
- [ ] Step 1 answers: what I call him, his cartoon look, my cartoon look, real details, real phrase
- [ ] Choose: narrator voice, style ref, 4 character refs, 10 keyframes, music candidate
- [ ] User test 1 (≥ 3 people, radio cut) and user test 2 (≥ 3 people, near-final cut): send answers verbatim
- [ ] Approve making the GitHub repo public
- [ ] Rewrite the report in my own voice → PDF/DOCX
- [ ] Upload the films (link opens without login), write and publish the post with the AI label on
- [ ] Record the ≤ 5-min walkthrough
- [ ] Submit Assignment 1 (repo link + report) and Assignment 2 (9:16 link + 16:9, walkthrough, post as attachments)
- [ ] Before the interview: reread DESIGN, EXPERIMENTS, FAILURES and runs.jsonl

### Submission checklist
- [ ] Public repo; `make film` from a clean clone works; README explains it
- [ ] storyboard.json + schema validated on every run; runs.jsonl complete
- [ ] DESIGN (audience before generation, 2 user tests ≥ 3 people each, the changes, every shot's reason) · ARCHITECTURE · EXPERIMENTS (≥ 10) · FAILURES · COSTS · ETHICS
- [ ] Film 60–90 s in 9:16 and 16:9; narration clear; score ducked; subtitles accurate; consistent characters; AI end card; −14 LUFS
- [ ] Walkthrough ≤ 5 min with a live single-shot regeneration
- [ ] Public post written by me, AI label on
- [ ] Report: all 7 sections, tied to evidence in the repo

---

## 15. Schedule (EAT)

| When | What | Cut-line if behind |
|---|---|---|
| Wed 25: now → +1.5 h | Step 0 | Skip the FLUX.2 test if Cloudflare is slow; use schnell |
| +1.5 h → +3 h | Step 1 | — |
| +3 h → +4.5 h | Step 2 → **send radio cut (test 1)** | Placeholder music can be silence + a fade |
| +4.5 h → evening | Step 3 (refs while test 1 replies come in; keyframes after the changes) | 2 candidates per shot instead of 3 |
| By ~22:00 | Step 4: push ACE-Step, then the Wan pilot + batch to run overnight | Animate only priority 1–5 |
| Thu 26: 08:00–09:30 | Pull clips and music, audition, rough cut | — |
| 09:30–13:00 | Step 5 → **send near-final cut (test 2)** | Fewer transitions; hard cuts only |
| 13:00–20:00 | Step 6 docs, release, report draft | Skip ceiling work |
| 20:00–22:30 | **[ME]** report rewrite, post, walkthrough, submit both | — |
| 22:30–23:59 | Buffer | — |
