# The Toolbox: report

B2W0 AI-Content Generation, Assignment 1 · 26 November 2026 ·
Repository: <https://github.com/estif-lul/the-toolbox>

**At a glance**
- **The film:** a 75.7 s animated short in 9:16 and 16:9. English narration, three lines of Dad's
  in Amharic, English subtitles, an original score ducked under the voice and a "Made with AI" end
  card. QC in both formats: −14.6 LUFS, true peak −1.2 dB.
- **The pipeline:** one contract, `storyboard.json`, and one stage per job:
  - narration: Gemini 3.8 Flash TTS
  - reference sheets and keyframes: FLUX.2 klein 4B on Workers AI
  - moving shots: Wan 2.2 TI2V-5B on Kaggle T4s
  - score: ACE-Step 1.5 on Kaggle
  - edit: FFmpeg

  `make film` rebuilds the film from a clean clone, with no keys.

- **Measured:**
  - 210 logged model calls and 184 cache hits.
  - 86 GPU-minutes on Kaggle T4s.
  - Paid: $0. At list price: about $0.17 plus the GPU time (COSTS.md).
  - 15 experiments, 17 failures, two user tests.
- **How it was made:** I directed the work and made the creative choices (story, voices,
  keyframes, score). The coding agent, Claude Code, wrote the pipeline code and drafted the
  documentation from the logs. It also judged which moving clips to keep (E15).

## 1. What I set out to make, and for whom

The film is about my dad, who never called anyone to fix anything. If it could be done at home, he
did it himself, and I was always one step behind him. His answer to every problem is the same two
words, *እስኪ እንየው*: "Let's look at it first."

The film walks through four of those moments: under the car with a torch, a rekebot built from a
few planks, a power cut, a leaking pipe. Then it moves forward: years later we fix things together,
he gives me his old toolbox, and at the end I call him to say "Dad, I fixed it myself." I chose this
story because everyone who knows him will recognise him in it, and that recognition is the point.

**The audience** is our family and friends, almost all Habesha, in Ethiopia and the diaspora. They
watch on phones, in WhatsApp and Telegram groups, often with the sound low. That fixed the form
before anything was generated (DESIGN.md §1):
- **Vertical first,** with a horizontal version for YouTube.
- **Burned-in subtitles** in a large, readable font (Atkinson Hyperlegible), because many people
  will watch without sound.
- **One clear subject per shot,** centred, so both crops keep it.
- **A hook in the first three seconds:** the red toolbox in a beam of light.

The feeling I wanted at the end is pride and warmth: "that is exactly him", and he now lives on in
me. A smile, not tears.

Dad and I appear only as cartoon characters with stock voices. No photo, likeness or voice of a real
person was used. Before anything was generated, Dad agreed in writing to the story, to his three
lines and to public posting (ETHICS.md §2).

## 2. What I learned from my audience

**Test 1: the radio cut (25–26 Nov).** It was the narration, Dad's lines and the subtitles on a
black screen over a placeholder pad, 75.7 s long. I sent it on WhatsApp with six questions
(DESIGN.md §4). The family and friends I sent it to found it fine as it was. Nobody was confused,
nobody found it too long, nobody flagged Dad's Amharic lines, and nobody asked for a change.

**Test 2: the near-final film (26 Nov).** This was the 9:16 film with pictures, score, subtitles and
end card, sent with seven questions (DESIGN.md §5). At that point only 2 of the 11 images moved; the
rest were slow Ken Burns moves over stills. Everyone answered. Their verdict: **"very good, given
it is a free model."** Nobody reported a character who stopped looking like himself, unreadable
subtitles or a wrong detail. Dad watched it too and was happy with it. For a film about him, his
was the reaction that counted most.

What this taught me:
- **The story and the length work for this audience.** Two rounds produced no confusion and no "too
  long". The 75 s, the subtitles and the three Amharic lines stayed as they were.
- **They forgive the technology, but they notice it.** "Given it is a free model" means they judged
  the film partly as a piece of technology. The stills between moving shots were visible and
  forgiven: for a family audience the story carries the film, not the motion (§4).
- **Consistency held up with real viewers.** What I worried about most was the boy growing into the
  man and Dad ageing (§3). It drew no comment in test 2.
- **My testing was weak, and I should say so plainly.**
  - In both rounds I got the answers as a conversational summary, not question by question. So I
    have no verbatim quotes and no single moment the audience picked out.
  - Neither test changed the storyboard. Every change to the film came from my own review: the
    rejected keyframes (FAILURES.md F12, F13, F15) and the rejected clips (F17).
  - I learned *that* the film works, not *which part* carries it. Next time I would ask one
    forced-choice question ("which shot would you cut?") and paste every reply into DESIGN.md as it
    arrives.

## 3. The hardest problem: making the family look like us

My audience will notice at once if Dad, or I, do not look like us. The image model kept making us
into someone else:
- **The boy's first sheets.** I described him as "a Habesha Ethiopian boy with brown skin", and
  **4 of 4** came out light-skinned (EXPERIMENTS.md E21). Dad, described the same way, was right in
  3 of 4.
- **It came back in new places.** Fixing the boy did not fix it everywhere. One of four grown-son
  sheets came out lighter. The hands-only inserts have no character sheet attached, and there the
  father's hands were light-skinned in 3 of 3 candidates for s04.
- **The style reference made it worse.** The style image (the red toolbox on a table) went with
  every image, and it carried its subject along with its style. 2 of 4 Dad sheets and 1 of 4 boy
  sheets put the figure at that table, and those sheets also lost the skin tone and the clothes
  (E22).

What fixed it:
1. **Words that leave no room.** I wrote "warm brown skin, the same skin tone as his father" for
   every age of the son, and "the father's warm brown hands" in every hands-only shot. The boy went
   from 0 of 4 right to 3 of 4.
2. **A chain of references instead of fresh draws.** The teen and the grown son are drawn from the
   chosen boy's sheet, and Dad at fifty from Dad's sheet. The prompt says "keep the family
   resemblance … but draw him at the new age". Dad at fifty came out as the same man in 4 of 4
   (E19).
3. **The style image only where it cannot leak:** the first sheets, and shots with no character or
   with the toolbox in view. Without it: 0 leaks in 27 images (E22).
4. **A check by eye on every candidate** before it can be chosen. Rejected sets stay in the repo
   (`outputs/refs/rejected/`, `outputs/keyframes/rejected/`), with their reasons in FAILURES.md.

The fix was then tested where it counts: in test 2, nobody said a character stopped looking like
himself. What I learned: this model's default for a cartoon child is light-skinned. It has to be
told, in words that cannot be misread, and then checked, every time.

Two other problems took real work:
- **Ten TTS requests a day for a 16-line film.**
  - Several lines go in one request with a long pause between them, and the audio is cut at the
    pauses.
  - Every cut is checked by having another model transcribe it back.
  - 9 requests made 30 takes. 20 of 21 cuts were right first time, and the check caught the one
    that was not (E20, F09).
- **Wan 2.2 on a free T4.**
  - 704×704×81 ran out of memory, even after I forced memory-efficient attention. So every clip is
    576 px and 2 s long (F16, E09).
  - The edit was built for short clips: each plays, then holds its last frame with a slow drift.
  - A frame-by-frame review kept 8 of 11 clips and sent three shots back to Ken Burns (E15, F17).

## 4. A suggested practice that beat my instinct: the Ken Burns fallback

The brief says: "The slow pan-and-zoom over a still (Ken Burns) is a respectable shot, and a
fallback when a clip fails." My instinct said the opposite. A film is moving pictures, the stills
are a placeholder until the video model delivers, and that is where the effort should go.

I built the fallback anyway, as a stage of its own. Every shot gets a Ken Burns clip first
(`make kenburns`), and the edit uses a Wan clip only where one exists and passes review. The
evidence that this was right:
- **A complete film existed on the first night,** before any GPU job: the rough cut (E08). It let
  me check crops, timing and subtitles early. It is also how the 16:9 crop cutting off Dad's head in
  s05 was caught, and fixed with an edit setting instead of new images.
- **User test 2 went out with 9 of 11 images as stills,** and the verdict was "very good". The
  stills did not stop the story from landing.
- **When Wan failed, nothing broke.**
  - Every clip ran out of memory at the target size (F16, E09), and three of the smaller clips
    morphed (F17).
  - Each of those shots went back to its Ken Burns move with one line in `storyboard.json`.
  - The re-render took 3 minutes and needed no GPU.
- **Motion is in the final film where it helps** (8 of 11 images), not because the film depends on
  it.

A second suggested practice also paid off: **a reference sheet before the keyframes.** Without the
sheets, the boy would not have grown into the same man (§3, E19).

## 5. A suggested practice that did not work for me: one reference image for every shot

The brief suggests "a character sheet, a style block and one approved reference image, then every
shot generated against them." I did exactly that at first: the chosen style image went with every
image as "the style reference (ignore its subject)".

It did not ignore its subject. FLUX.2 klein copied the style, and the subject too:
- The style image's table and toolbox turned up in 2 of 4 Dad sheets and 1 of 4 boy sheets.
- In all 3 candidates for s01, the toolbox sat on a stool like the one in the style image, not on
  the floorboards I asked for.
- The sheets that leaked also lost the character's skin tone and clothes (E22).

Without the style image, the sheets drawn from a parent sheet and the keyframes that only got
character sheets kept the look: 0 leaks in 27 images.

What I do instead: the style image goes only to the first sheets and to shots with no character or
with the toolbox in view. The character sheets carry the style everywhere else (`keyframe_jobs` in
`pipeline/keyframes.py`). The practice is right that consistency comes from references, not text.
For this model it is wrong that one reference can go everywhere. A reference image is a picture of
something, and the model treats it that way.

A smaller one: **"Generating narration line by line, one file per shot."** One file per line, yes;
one request per line, no. TTS allows 10 requests a day per model, and one request per line would
have needed 30 for the narration and auditions: three days of one model's quota. Batching, with a
heard-back check, did it in 9 (E20).

## 6. Beyond the floor

I did not finish one of the listed ceiling projects. The open-vs-frontier benchmark is designed but
not run, because I had no paid access (docs/PAID_LANE.md). Where I went further is a question that
came up three times: **can a model check another model's work?**
- **Hearing the narration back (E20, F09).** Every TTS cut is transcribed by Gemini 3.5 Flash-Lite
  and compared with its text.
  - On English lines it scores 0.92–1.00.
  - It caught a real error that the length check had passed: s07's "Then… silence." had been cut
    into the next shot.
  - It is now a stage (`make narration-check`).
- **The same check on Amharic (E18).**
  - On Dad's three lines it scored 0.40–0.63, while I, a native speaker, judged all three natural.
    The transcriber is the weak link, not the voice.
  - So the check shows Amharic scores but does not fail them, and a native speaker's ear decides.
- **Pre-listening to the score (E14).**
  - I asked a multimodal model to describe each of the three score candidates.
  - It found no vocals and no glitches, which was true.
  - But its descriptions mostly repeated the brief I had given it, and it could not tell the
    candidates apart.

**What this taught me:** a model is a good negative check (a missing word, a vocal in an
instrumental, a glitch) and a poor judge. It is weakest in the language it knows least, and it hears
what you told it to expect. So every choice that needed taste (voices, keyframes, the score, the
clips) stayed with a person, and the logs say which person.

I also recorded one negative result so nobody has to repeat it: on a free T4, forcing
memory-efficient attention does not make Wan 2.2 fit at 704×704×81 (E09, with the timings).

## 7. What I would build next

- **Trim before the hold.**
  - The review showed that a clip is judged mostly by its last frame, because the edit holds it
    longest (F17).
  - A per-shot trim would keep the good first second of a clip instead of throwing the whole clip
    away. For example, the start of the lid opening in s09.
- **One motion per prompt.**
  - Two of the rejected clips had asked for two things at once ("the lid lifts" and "the trays
    unfold").
  - I would rewrite those prompts to one small motion and rerun only those shots. The cache makes
    that three jobs, not eleven.
- **The paid lane** (docs/PAID_LANE.md):
  - the same Wan code on a rented 24 GB GPU, in bf16 at 720p;
  - the open-vs-frontier benchmark with a blind preference test.
- **Better user tests:** one forced-choice question per test, and every answer pasted verbatim.
- **A small family app:** each relative records one phrase of Dad's, and it becomes a shot.

## Evidence

| What | Where |
|---|---|
| Audience, intent, both user tests, a reason for every shot | [DESIGN.md](../DESIGN.md) |
| Stages, contract, cache keys, failure handling | [ARCHITECTURE.md](../ARCHITECTURE.md) |
| 15 experiments (E01–E04, E08, E09, E13–E15, E18–E23) | [EXPERIMENTS.md](../EXPERIMENTS.md) |
| 17 failures (F01–F17) | [FAILURES.md](../FAILURES.md) |
| Latency, GPU minutes, list-price equivalent | [COSTS.md](../COSTS.md) |
| Consent, privacy, labelling, licences | [ETHICS.md](../ETHICS.md) |
| Every model call, cache hit, retry and Kaggle job | [runs.jsonl](../runs.jsonl) |
| The contract and its schema | [storyboard.json](../storyboard.json), [schema/](../schema/storyboard.schema.json) |
| The films and their QC | [outputs/final/](../outputs/final/) |
