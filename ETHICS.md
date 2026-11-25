# ETHICS — consent, privacy, labelling and licences

Written before any generation (first commit). Updated as models are chosen; finalised in Step 6.

---

## 1. Cartoon-only decision

- The characters in this film are **fictional cartoons inspired by my father** and by me. They are
  generated from text descriptions only.
- **No photo, likeness or voice of any real person is used as input or reproduced.** No image of
  Dad or of me is uploaded to any service. No voice is cloned.
- All voices are **Gemini TTS stock (prebuilt) voices**: one for the narrator, a different one for
  the cartoon Dad. Neither is a recording or clone of a real person.
- Other family members appear only as **unnamed, soft background figures** (e.g. silhouettes
  cheering when the lights come back). They are not designed to be recognisable. If any specific
  relative is ever meant to be recognisable, their agreement is recorded in the table below first.

## 2. Consent record

The brief's zero-score gate covers any real person "shown or voiced". Although only cartoons and
stock voices are used, the story is about my real father, so I record his agreement to the story
being told and posted publicly.

| Person | Role in the film | Shown / voiced? | What they agreed to | Status | Date | Medium |
|---|---|---|---|---|---|---|
| My father ("Dad") | Inspiration for the cartoon Dad; his phrases are spoken by a stock voice | Cartoon only; stock voice; no likeness or voice used | The story, the three Amharic lines put in the cartoon's mouth, and public posting | **Pending** | — | WhatsApp / voice message |
| Me | Narrator (cartoon at three ages) | Cartoon only; stock voice | — (author) | n/a | — | — |
| Other family members | Unnamed background silhouettes | No (not recognisable) | — | n/a | — | — |

The three lines the cartoon Dad speaks (to be confirmed with him as words he would say):
1. *እስኪ እንየው* — "Let's look at it first."
2. *ቀስ በቀስ እንቁላል በእግሩ ይሄዳል* — "Slowly, slowly, the egg walks on its own legs." (a common proverb)
3. *ጎበዝ ልጄ* — "Well done, my son."

## 3. Privacy rule (prompts sent to free endpoints)

Several free endpoints may use what is sent to them to improve their models. Therefore prompts
and TTS text contain:
- **No real names** beyond "Dad"; no surnames; no names of relatives.
- **No addresses, neighbourhoods, licence plates, workplaces, phone numbers or emails.**
- No car brand or plate (the car is described only as "an old boxy white 1980s sedan").
- Setting details are generic and shared by many Ethiopian homes (a sky-blue metal gate, a
  corrugated-iron roof, a water tank), not identifying.
- `pipeline/common/storyboard.py` runs a soft lint that flags digit runs that look like phone
  numbers or plates, and email addresses, before any model call.
- Smoke tests use neutral prompts only ("a red apple on a table", "Testing one two three").

## 4. Style

The look is described by its qualities (warm, hand-painted, soft golden light, paper texture,
rounded shapes). **No living artist or studio is named** in any prompt.

## 5. Labelling plan

- **In the film:** a visible end card (≥ 3 s) that says **"Made with AI"**, that the characters are
  fictional cartoons, and which models made the images, video, music and voices.
- **In the file:** MP4 metadata `comment="Made with AI — see end card"`. Provenance from any
  source (SynthID, C2PA, watermarks) is never stripped.
- **When posting:** the platform's AI disclosure is switched on even though the film is a cartoon:
  YouTube "altered or synthetic content", TikTok "AI-generated content", Meta "AI info"
  **[VERIFY the current toggle names when posting, Step 6]**.
- **In the post:** the text says the film was made with AI and how.

## 6. Licences (filled in as models are chosen; every row verified before release)

| Component | Used for | Licence / terms | Output use | Status |
|---|---|---|---|---|
| Gemini 3.x Flash / Flash-Lite (Gemini API, free tier) | Script / storyboard draft | Gemini API Terms of Service; free-tier data may be used to improve Google products | Generated content may be used; Google claims no ownership | **[VERIFY]** model id + terms |
| Gemini Flash TTS (Gemini API, free tier) | Narration and Dad's lines (stock voices) | Gemini API Terms of Service (as above) | As above; output may carry SynthID | **[VERIFY]** |
| FLUX.2 klein 4B (Cloudflare Workers AI) | Keyframes, reference sheets | Apache 2.0 (per the brief) + Cloudflare terms | Commercial use allowed | **[VERIFY]** which klein variant (4B Apache 2.0 vs 9B non-commercial) |
| FLUX.1 schnell (Cloudflare Workers AI) | Keyframe fallback | Apache 2.0 + Cloudflare terms | Commercial use allowed | **[VERIFY]** |
| Wan 2.2 TI2V-5B (Kaggle) | Moving shots | Apache 2.0 (per the brief) | Allowed | **[VERIFY]** model card |
| ACE-Step 1.5 (Kaggle) | Score | MIT; trained on licensed, royalty-free and synthetic data (per the brief) | Commercial use allowed (per the brief) | **[VERIFY]** repo licence |
| FFmpeg | Assembly, Ken Burns, mixing | LGPL/GPL (the gyan.dev full build is GPL) | Tool only; no licence on outputs | **[VERIFY]** |
| Subtitle / end-card font | Burned-in subtitles, end card | SIL Open Font License (OFL) | Allowed; licence file in `assets/fonts/` | Chosen in Step 5 |
| Python libraries | Pipeline code | Various permissive (listed from `uv.lock` in Step 6) | — | Step 6 |
| This repository's code | — | To be chosen (MIT intended) | — | Step 6 |

## 7. Data-retention note for the paid lane

Before any paid provider is adopted (PLAN.md §10), its licence, output terms, watermarking /
provenance (SynthID, C2PA) and data-retention policy are checked and added to the table above.
