# EXPERIMENTS — hypothesis → change → result

Each entry is written **when the experiment runs**, tied to evidence (run_ids in runs.jsonl,
cache keys, file paths, measured numbers). One variable changes at a time; the seed stays fixed
when comparing prompts. Target: at least 12 real entries.

Template:

```
## E07 — <short title>
- Date / run_id(s):
- Hypothesis: If I <change>, then <expected effect> because <reason>.
- Change (one variable): …        Held fixed: seed=…, prompt=…, model=…
- Result (measured): latency …, calls …, observation …, who judged …
- Decision: keep / revert / follow-up E0x
- Evidence: runs.jsonl lines (run_id …), files outputs/…/<key>.png
```

---

Step 0 produced the baseline measurements in COSTS.md "Free tiers as found" and the smoke results
in `outputs/smoke/summary.json`.

## E01 — script: AI storyboard draft vs the hand-written storyboard
- Date / run_id: 2026-11-25 15:49 EAT, run `20261125-154916-fae2` (`make script`). An earlier run,
  `20261125-154638-d856`, produced nothing (FAILURES.md F08, F05).
- Hypothesis: If the text model drafts the whole storyboard from the treatment and the schema, then
  it will get the structure right in about a minute, but it will miss the family and cultural
  specifics and the pipeline conventions it can only guess, because the brief is a 150-word
  treatment, not the family's memories.
- Change (one variable): who writes `storyboard.json`: Gemini (`gemini-3.5-flash`, after 3.8 Flash
  answered 503) vs me. Held fixed: the same brief (DESIGN.md §3 without the "Shot reasons" table,
  which is the human answer), the same schema, and the rules in `pipeline/script.py`;
  temperature 0.8. Exact prompt: `outputs/script/draft/1bcf5d4e478063af.prompt.txt`.
- Result (measured):

  | | AI draft | Hand-written v1 | v1 after merging |
  |---|---|---|---|
  | Shots | 10 | 10 | 10 |
  | Narration words | 144 | 142 | 146 |
  | Estimated length incl. end card (2.3 words/s) | 76.5 s | 80.5 s | 82.2 s |
  | Schema errors | 0 | 0 | 0 |
  | Semantic errors | **7** (every `derived_from` points at itself) | 0 | 0 |
  | Latency / tokens | 64.0 s; 5,774 in, 6,010 out, 11,680 thinking | written in this session | |

  The draft passed the schema on the first try (helped by the output constraint, F08) and its
  length was on target. The problems were in content, not in form:
  - **Voices made up for another product:** `en-US-Neural2-D` and `am-ET-Wavenet-B` are
    Google Cloud TTS names; the pipeline uses Gemini TTS stock voices (e.g. "Kore").
  - **The emotional lift is gone:** the plumbing memory takes two shots (s06, s07) and the house
    lighting up after the power cut, the only moment of joy, disappears.
  - **Culture flattened:** the rekebot became "our coffee table"; Dad became "an Ethiopian man"
    with no skin tone in any description (an image model then picks one).
  - **The locked ending line is gone:** "Dad, I fixed it myself" became "I fixed it myself, then
    called him", which reports the moment instead of letting us hear it.
  - **Telling instead of showing:** "He taught me that patience was his secret tool";
    "everyone panicked" (the hand version's "everyone said: call someone" sets up the contrast
    with s01's "never called anyone").
  - **GPU priorities in story order** (1–10) instead of importance; nearly every transition a cut;
    s09 uses the new toolbox, not the older one; the s10 image prompt asks the image model for a
    split screen (assembly does that from the two layers).
  - **No AI labels on the end card** beyond "Made with AI" (no "fictional cartoons", no credits).
- What the draft did better, merged into `storyboard.json` by hand:
  1. **It names what breaks** at the end: "So when my own tap leaked, I opened the latch." In my
     version the tap only appeared in the background of s09, so "I fixed it myself" had no
     object. s09 now says "Last week, my kitchen tap started leaking. And I heard him." (tenses
     in s10 follow: "So I called him", "And I could hear him smiling").
  2. **The grown son holds a wrench while on the phone**, a mirror of Dad's spanner on the other
     side of the split screen. My s10 reason already said "both holding a tool", but my prompt
     did not show it.
  3. Style block: "storybook" added; negative prompt: "realistic faces" added (both protect the
     cartoon look).
- Decision: keep the hand-written storyboard as the contract, with the 3 merges above. The AI
  draft stays in the repo as evidence (`storyboard.draft.json`) and is never read by a stage.
- Evidence: runs.jsonl run `20261125-154916-fae2` (one `fallback`, one `model_call` ok);
  `outputs/script/draft/1bcf5d4e478063af.{json,prompt.txt,report.json}`;
  `outputs/script/manifest.json`; the merge is the `story:` commit of storyboard v1.

## E02 — tts: three stock voices for the narrator
- Date / run_id: 2026-11-25 21:06 EAT, run `20261125-210624-3fd2` (`make audition ROLE=narrator
  MODEL=gemini-3.8-flash-lite-tts`).
- Hypothesis: If the same two lines are read by the three candidate voices, one of them will sound
  like "a young man remembering his father" (warm, unhurried) more than the others, because the
  voices are documented with different characters: Achird "Friendly", Umbriel "Easy-going",
  Iapetus "Clear".
- Change (one variable): the stock voice. Held fixed: the lines (s01:0 *"My dad never called anyone
  to fix anything."* and s10:1 *"Dad, I fixed it myself."*, the first and the last thing the
  narrator says), each line's style from the storyboard, the model (`gemini-3.8-flash-lite-tts`, to
  save Flash TTS's 10 requests a day for the final audio), one request per voice.
- Result (measured; speech only, silences trimmed):

  | Voice | Both lines | English words/s | Request latency |
  |---|---|---|---|
  | Achird | 6.26 s | 2.08 | 6.9 s |
  | **Umbriel** | 7.40 s | 1.76 | 20.3 s |
  | Iapetus | 7.11 s | 1.83 | 4.2 s |

  Listen: `outputs/narration/audition/narrator/3.8-flash-lite/sheet.wav` (Achird, Umbriel, Iapetus,
  1.5 s apart); one file per voice beside it; numbers in `audition.json`.
- Decision: **Umbriel**, chosen by ear by me. Why: **[ME] one line in my words.** Caveat: the
  audition ran on Flash-Lite and the film uses Flash TTS; the same voice reads faster on Flash
  (s01: 4.02 s on Flash-Lite, 3.38 s on Flash), so the final pace was measured again (E03).
- Evidence: runs.jsonl run `20261125-210624-3fd2` (3 `model_call`, shot_id `s01:0,s10:1`);
  `outputs/narration/batches/{f5c362441529f9d7,779ae44dda0a7b39,dea769c57f451a69}.{wav,json}`.

## E03 — tts: style instruction vs none (narrator, Umbriel)
- Date / run_id: 2026-11-25 21:13 EAT, run `20261125-211339-5ae8` (`make audition ROLE=narrator
  VOICES=Umbriel NO_STYLE=1 MODEL=gemini-3.8-flash-lite-tts`); final pace from run `20261125-211359-ae9a`.
- Hypothesis: If the style instruction ("warm and unhurried, a quiet smile in the voice, a young
  man remembering his father") is left out, the read will be faster and flatter, because pace is
  part of what the instruction asks for. Measured as words per second on the same two lines.
- Change (one variable): style on / off. Held fixed: voice Umbriel, the two E02 lines, Flash-Lite TTS.
- Result (measured): with the style **1.76 words/s** (7.40 s); without **2.50 words/s** (5.20 s).
  The instruction slows the read by 30%. On Flash TTS with the style, the whole narration runs at
  **2.66 words/s** (137 English words in 51.6 s), faster than Flash-Lite with the same style.
- Decision: keep the style. At the measured pace the film is 75.7 s including the 3 s end card,
  in the middle of the 60–90 s window, so no line needs trimming and there is room for user-test
  changes. Without the style the film would be ~10 s shorter but read like an announcement.
- Evidence: `outputs/narration/audition/narrator/3.8-flash-lite-nostyle/`; `outputs/narration/timing.json`.

## E04 — tts: a separate, deeper stock voice for Dad
- Date / run_id: 2026-11-25 21:08 EAT, run `20261125-210752-2005` (`make audition ROLE=dad`).
- Hypothesis: If Dad's three Amharic lines are read by a different, deeper stock voice than the
  narrator, they will stand out as *his* voice in the son's memory, because the contrast tells the
  listener who is speaking even with the sound low (the aunt persona in DESIGN.md §1).
- Change (one variable): the Dad voice (Algenib "Gravelly", Charon "Informative", Orus "Firm").
  Held fixed: the three lines in Ge'ez script with their storyboard styles, **Flash TTS** (the
  final model, so the chosen voice's takes are already the final audio), one request per voice.
- Result (measured, trimmed):

  | Voice | *እስኪ እንየው* | the proverb | *ጎበዝ ልጄ* | Request latency |
  |---|---|---|---|---|
  | **Algenib** | 0.72 s | 2.21 s | 2.00 s | 23.5 s |
  | Charon | 0.76 s | 2.80 s | 1.94 s | 5.8 s |
  | Orus | 1.88 s | 3.63 s | 2.07 s | 6.4 s |

  Listen: `outputs/narration/audition/dad/3.8-flash/sheet.wav` (Algenib, Charon, Orus).
- Decision: **Algenib**, chosen by ear by me. Why: **[ME] one line in my words.** Because the
  audition used the storyboard's own lines, styles and the final model, choosing Algenib made his
  three lines cache hits in `make narration`: the audition cost no extra request. Whether the
  contrast "lands" with the audience is user test 1, question 5.
- Evidence: runs.jsonl run `20261125-210752-2005`; the `cache_hit` lines for s05:1, s08:1 and
  s10:2 in run `20261125-211359-ae9a`.

## E18 — tts: Amharic in Ge'ez script, judged by a native speaker
- Date / run_id: 2026-11-25 21:08 EAT (audio, run `20261125-210752-2005`); 21:16–21:25 (machine
  transcription, runs `20261125-211616-6f20`, `20261125-212001-8278`).
- Hypothesis: If Dad's lines are sent in Ge'ez script with "Speak in Amharic: …" in the style, the
  TTS will pronounce them acceptably, because the speech docs list Amharic for both TTS models.
  Fallbacks planned: the transliteration in `tts_text` (*Eski, enyew*), then English in the same voice.
- Change: none needed. Held fixed: the three lines as written, Flash TTS, three voices (E04).
- Result:
  - **By ear (me, native speaker): all three lines natural** in Algenib (pronunciation, stress,
    one consistent person). No transliteration or English fallback was needed.
  - **By machine:** Gemini 3.5 Flash-Lite transcribed the same Algenib audio as *"ስኪንew"*,
    *"እሱ በቃ እሱ እንቁላል በግሮሄዳል"* and *"ጎቪስ ልች"*: similarity 0.50, 0.63 and 0.40 to the text
    (it got *እንቁላል* right). On the English lines the same check scores 0.92–1.00.
- Decision: keep the Ge'ez lines. The automatic narration check shows the score for Amharic lines
  but does not fail them: the transcriber is the weak link, not the voice. A native speaker's ear
  decides (and Dad himself hears them in the radio cut: DESIGN.md §4, ETHICS.md §2).
- Evidence: `outputs/narration/verify_report.json`; `outputs/narration/audition/dad/3.8-flash/`.

## E20 — tts: many lines per request, cut apart at the pauses
- Date / run_id: 2026-11-25 21:06–21:25 EAT, all Step 2 runs above.
- Hypothesis: If several lines go into one TTS request (one turn per line with its own style, the
  documented `<long pause>` tag between turns), the response can be cut back into lines reliably
  by choosing the pauses whose spacing matches each line's text length, because the model leaves
  a longer pause between turns than inside a sentence. That turns "one request per line" (16 for
  the film, 30 for this step) into a handful, inside the free tier's 10 requests a day.
- Change: batch size (1 line per request → up to 8). Held fixed: voices, styles, models.
- Result (measured):
  - **9 TTS requests produced 30 line takes** (auditions + final). One request per line would
    have needed 30: three times one model's daily quota.
  - **21 cuts, 20 right first time, 1 wrong** (F09): s07's dramatic pauses inside "Patience.
    Then… silence." were as long as a between-line pause (0.94–0.98 s vs 1.04 s). The length
    check passed it; hearing each line back caught it, and the repair fixed it from the saved
    response with no TTS call.
  - Pause left between turns: 0.61–1.47 s (Flash-Lite, 2-line batches), 1.04–2.56 s (Flash, 8 and
    5 lines), 2.1–4.6 s (Flash, Dad's Amharic). `<long pause>` is not a fixed length.
  - One edited line still costs exactly one request: a cache miss on one line makes a batch of one
    (`tests/test_narration.py::test_editing_one_line_costs_one_request_for_that_line`).
- Decision: keep batching (up to 8 lines, `batch_lines` in config/providers.yaml) **with** the
  heard-back check (`make narration-check`) after every batch run.
- Evidence: `outputs/narration/batches/*.json` (each cut, its pause, its length ratio, any
  repair); `outputs/narration/verify_report.json`; runs.jsonl stage `narration_check`.

## E21 — image: skin tone drifts lighter unless the text insists (the boy and the grown son)
- Date / run_id: 2026-11-25 22:00–22:15 EAT, runs `20261125-220047-5f96` (v1), `20261125-220344-f836` (v2),
  `20261125-221544-195e` (grown son).
- Hypothesis: If the boy's description says "brown skin" and "a Habesha Ethiopian boy", the
  sheets will show a brown-skinned Habesha boy, because the same wording worked for Dad.
- Change (one variable): the skin-tone wording. Held fixed: FLUX.2 klein 4B, 4 steps, seeds
  1201–1204, the chosen style image as reference, the sheet prompt.
- Result: **v1 "brown skin": 4 of 4 boys light-skinned** (peach to light tan;
  `outputs/refs/rejected/contact_me_child_v1_light_skin.png`). Dad, described the same way,
  came out brown-skinned in 3 of 4 (the fourth was a light-skinned man in a polo shirt, E22).
  **v2 "with warm brown skin, the same skin tone as his father": 3 of 4 right**; the fourth
  was again a light-skinned boy at the style image's table (E22). The grown son, drawn from the
  chosen boy's sheet: 3 of 4 right, 1 visibly lighter. In keyframes, the **hands-only inserts**
  (s04, which has no character attached) came out with light-skinned hands in 3 of 3.
- Decision: the descriptions now say "warm brown skin" for every age of the son; hands-only
  shots say "the father's warm brown hands" (s04, s07). Every candidate is checked for this
  before it can be chosen, and rejected sets are kept in `outputs/*/rejected/`.
  The image model's default for a cartoon child is light-skinned; it has to be told, and
  checked.
- Evidence: the contact sheets above; `outputs/keyframes/rejected/s04_v1_contact.png`.

## E22 — image: what a reference image carries besides its style
- Date / run_id: 2026-11-25 22:00–22:22 EAT (the refs and keyframe runs).
- Hypothesis: If the style image (the red toolbox on a table) is passed with every image as "the
  style reference (ignore its subject)", the line work and palette will carry over and the table
  and toolbox will not, because the prompt says which reference is for what.
- Change: which references go with which image. Held fixed: the model, steps, seeds.
- Result: the style carried over everywhere, and so did the subject: **2 of 4 Dad sheets and 1 of
  4 boy sheets put the figure at the style image's table** (one with the toolbox), and both of
  those also lost the character's skin tone and clothes (E21). In s01 all 3 candidates put the
  toolbox on a stool like the style image's, not on floorboards as written. Without the style
  image, sheets drawn from a parent sheet (dad_now, the teen, the grown son) and keyframes
  that only got character sheets (s05, s06, s08, s10b) kept the look: **0 leaks in 27 images**.
- Decision: the style image goes only to the first sheets (style + dad + boy) and to keyframes
  with no character or with the toolbox in shot (s01, s04, s07, s09, s10a). The character sheets
  carry the style everywhere else (`pipeline/keyframes.py keyframe_jobs`).
- Evidence: `outputs/refs/contact_dad.png` (#1, #3), `outputs/refs/contact_me_child.png` (#0),
  `outputs/keyframes/s01/contact.png`.

## E19 — image: the age chain (teen and grown son drawn from the boy, Dad at fifty from Dad)
- Date / run_id: 2026-11-25 22:08–22:15 EAT, runs `20261125-220711-4e2e`/`-220720-16c9` (v1), `20261125-221544-195e` (v2).
- Hypothesis: If the teen, the grown son and Dad at fifty are drawn with the chosen younger
  sheet as a reference, they will read as the same person at another age, because the face comes
  from the image rather than from a new random draw.
- Change: v1 passed the parent sheet with the default sentence ("keep each person's face, skin
  tone, hair and clothes exactly as in their reference"); v2 says "keep the family resemblance
  (face shape, eyes, skin tone, hair texture) and its art style, but draw him at the new age,
  with the body proportions and clothes described". The teen's "a faint moustache" was replaced by
  "a tall, lanky teenager with long arms and legs and a longer, thinner face".
- Result: **Dad at fifty: 4 of 4 clearly the same man**, greyer (chosen: #2, then the pencil
  edit #4, E23). **Teen v1: 4 of 4 kept the eight-year-old's body** and drew the faint moustache
  as a full cartoon moustache (`outputs/refs/rejected/contact_me_teen_v1_child_body_moustache.png`).
  **Teen v2: no moustache, a longer face, but still about 12–13** in this big-head storybook
  style (chosen: #0, the lankiest). The grown son, now drawn from the boy (`derived_from:
  me_child` instead of the teen, so a weak teen sheet cannot spread to s09 and s10): 3 of 4
  plausible, chosen #2 (beard, overshirt, the most adult face). Judged by me; the "same person"
  check by a second person is the near-final user test.
- Decision: keep v2. The teen appears only in s08, next to Dad, where his height relative to Dad
  matters more than his face.

## E23 — image: removing one detail from a chosen sheet by editing it (the pencil)
- Date / run_id: 2026-11-25 22:12 EAT, run `20261125-221226-c348` (`make revise`).
- Hypothesis: If the chosen sheet is passed as the only reference with "Edit reference image 1:
  remove the yellow pencil from behind his ear. Keep everything else exactly as it is", the pencil
  goes and the face I chose stays, because an edit starts from the image instead of a new draw.
- Change: the instruction (2 candidates each for Dad #0 and Dad at fifty #2). Held fixed: model, steps.
- Result: **4 of 4 removed the pencil and kept the face, clothes, pose and background**. Cost:
  4 images (~500 neurons) instead of 8 new sheets and another round of choosing. I asked for the
  change after seeing the sheets: the pencil was drawn very large and added nothing.
- Decision: keep (Dad #4, Dad at fifty #4); "a yellow pencil behind his right ear" is removed from
  both descriptions so no keyframe asks for it. `make revise ITEM=… FROM=… EDIT=…` is now a stage
  command; the manifest records `revised_from` and the instruction.

## E08 — edit: does "subject centred" survive both crops?
- Date: 2026-11-25 22:55–23:05 EAT, the rough cut (`make rough`).
- Hypothesis: If every image prompt asks for the subject centred with empty space around it, the
  centred 576-wide 9:16 column and 576-high 16:9 band will both keep the subject, because the
  central area is what both crops share.
- Result: **9:16 kept every subject. 16:9 cut the top of Dad's head in s05** and the hair of the
  grown son in s09: standing full figures fill the square's height, and a centred 16:9 band drops
  the top 22%. The crop previews on the contact sheets (orange 9:16, blue 16:9) show this before
  any animation; the first rough cut confirmed it.
- Decision: move the band per shot with `crop_focus.y` (an edit only: no image is regenerated):
  s05 0.40, s09 0.45, s10a/s10b 0.45, s02 0.58 (to keep their feet). Re-checked on frames of the
  rebuilt rough cut. Step 5 checks every shot this way.

## E13 — music: three seeds of one caption, chosen by ear under the narration
- Date / run_id: 2026-11-26 10:15 (push, `20261126-101457-b2e4`) → 10:32 (pull + ingest,
  `20261126-103235-dade`); Kaggle kernel `toolbox-music` v1, jobs.json `8709d6fe64e4`.
- Hypothesis: If the caption fixes the texture (krar, acoustic guitar, washint, sparse, slow) and
  BPM / key go in their own fields (80, D major), then three seeds give three usable variations, and
  the choice is about which one sits best under the voice, not which one is "good".
- Change (one variable): the seed (301 / 302 / 303). Held fixed: caption, 80 BPM, D major, 4/4,
  80 s (the film + a 4 s tail), instrumental, ACE-Step 1.5 turbo, 8 steps, DiT only (no LM "thinking").
- Result (measured):
  - 3 of 3 candidates usable: no vocals, nothing broken heard.
  - 6.6 s of GPU per candidate on a T4 (peak 7.8 GB). The whole kernel took 3.5 min, of which
    1.5 min was installing the repo's locked environment (`uv sync`: torch 2.10 + cu128 on Kaggle's
    driver) and the rest downloading weights.
  - Loudness (before mixing): c1 −15.9 LUFS, LRA 3.4; c2 −15.7, LRA 3.2; c3 −15.9, LRA 4.2; c3 has an
    ~11 s intro before its melody. The auditions are the radio cut once per candidate, the score
    ducked under the narration (`outputs/cuts/audition_c1..3.mp4`).
- Decision: **c1 (seed 301)**, chosen by me by ear. Why: **[ME] one line: texture, whether it
  fights the voice, the ending.** Recorded with `make choose ITEM=main PICK=1`.
- Evidence: `outputs/music/main_c{1,2,3}/`, `outputs/music/auditions.json`,
  `outputs/music/kaggle/8709d6fe64e4/` (results.jsonl, env.json, the kernel log).

## E14 — music: can a model pre-listen for me?
- Date: 2026-11-26 ~10:37 EAT, `scripts/describe_music.py` (3 calls to gemini-3.5-flash-lite with
  the candidate as audio, stage `music_check`).
- Hypothesis: If a multimodal model describes each candidate (instruments, vocals, artifacts,
  structure, ending), it will narrow the choice before I listen, the way the transcription check
  caught a bad narration cut (E20).
- Result: it found no vocals and no artifacts in any candidate, which is consistent with what I
  heard. But all three descriptions largely **repeat the brief back**: "fits the brief perfectly",
  "krar, guitar, washint", "gentle, nostalgic". It does not tell the candidates apart, and it named
  instruments from the prompt it was given.
- Decision: use it only as a negative check (vocals, glitches); the choice stays a human one. A
  better prompt would not give it the brief at all ("describe what you hear").
- Evidence: `outputs/music/describe.json`.
