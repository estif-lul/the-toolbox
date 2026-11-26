# Report draft: "The Toolbox"

> A draft built from the repository's evidence, for me to **rewrite in my own voice** before
> exporting it to PDF/DOCX. Every claim links to the file that backs it. **[ME]** marks what only I
> can write. Brackets with "pending" are filled when user test 2 comes back.

## 1. What I set out to make, and for whom

A 75-second animated short about my dad, who fixes everything himself and taught me to do the same.
His way of facing any problem is one phrase, *"እስኪ እንየው"* ("Let's look at it first"). It
ends with me, grown, calling him to say I fixed something myself.

The audience is our family and friends, almost all Habesha, in Ethiopia and the diaspora. They watch
on phones in WhatsApp and Telegram groups, often with the sound low. So the film is vertical first,
with burned-in subtitles and one clear subject per shot, and there is a horizontal version for
YouTube. The feeling I wanted at the end is pride and warmth: "that is exactly him", and he is now
in me (DESIGN.md §1).

It is made by a small pipeline:
- `storyboard.json` is the contract between stages.
- Free models do the work: Gemini TTS for the voices, FLUX.2 klein for the pictures, Wan 2.2 and
  ACE-Step on Kaggle GPUs for the motion and the score.
- FFmpeg assembles both formats.

Every call is logged and every output cached, so changing one line regenerates one shot
(ARCHITECTURE.md).

**[ME]** Why this story, in two or three sentences of my own.

## 2. What I learned from my audience

- **Test 1 (radio cut, before any picture):** the narration, Dad's three Amharic lines and the
  subtitles on black, 75 s. The people I sent it to found it OK and asked for no change
  (DESIGN.md §4). That told me the story and the length hold up as sound alone, but it was thin
  evidence: I did not collect answers question by question.
  **[ME]** What I would do differently: ask for one concrete answer, e.g. "which line would you cut?"
- **Test 2 (near-final film):** pending. Same questions, plus whether the characters feel like the
  same people throughout and whether the subtitles are readable (DESIGN.md §5).
  **[ME]** Quotes, the pattern, and the change it caused (with its commit).
- **From Dad:** he agreed to the story and to his three lines being said by a computer voice in a
  cartoon (ETHICS.md §2). **[ME]** His reaction to hearing them.

## 3. The hardest problem and how I solved it

Candidates, all with evidence. Pick one and tell it as a story:

- **Making the boy look like us.** The image model drew the boy light-skinned in **4 of 4** first
  sheets, although the text said "brown skin". The same happened to the grown son, one Dad sheet,
  and even the hands in a hands-only shot.
  - Fix: write "warm brown skin, the same skin tone as his father" for every age, and "the father's
    warm brown hands" in hands-only shots.
  - Check every candidate by eye for drift before it can be chosen.
  - Evidence: EXPERIMENTS.md E21, ETHICS.md "Representation check", rejected sets in
    `outputs/refs/rejected/`.
- **Ten TTS requests a day for a film of 16 lines.**
  - Send several lines in one request with a long pause between them, then cut the audio at the
    pauses (a small dynamic program matches pause lengths to text lengths).
  - Every cut is checked by having another model transcribe it back. That caught a cut in the wrong
    pause (s07 lost "Then… silence." to s08), which was repaired without a new request.
  - The whole narration is 3 requests. Evidence: EXPERIMENTS.md E20, FAILURES.md F09.
- **Wan 2.2 on a free T4.**
  - The pilot ran out of memory at 704×704×81: the default attention path builds a ~5 GB attention
    matrix. A fallback ladder made 2 s clips at 576 px instead.
  - Forcing PyTorch's memory-efficient attention: result pending.
  - Evidence: FAILURES.md F16, `outputs/shots/kaggle/`.

## 4. A suggested practice that beat my instinct

- **A pilot job before the batch.** My instinct was to push all ten Wan shots overnight. The
  pilot (2 shots, 15 min) showed the out-of-memory fallback and the real minutes per clip, so the
  full batch went out with the fix instead of burning an hour of GPU on 2-second clips.
  Evidence: commit `adae6e9`, `outputs/shots/kaggle/45eece612b0b/results.jsonl`.
- **Crop previews before animating.** The contact sheets draw the 9:16 and 16:9 boxes on every
  candidate. They showed the 16:9 band cutting off Dad's head in s05 before anything was animated.
  The fix was an edit setting (`crop_focus.y`), not new images (EXPERIMENTS.md E08).

## 5. A suggested practice that did not work (for me)

- **Attaching the style image to every picture for consistency.** It carried more than style: its
  table and toolbox appeared in shots that should not have them. It now goes only to the first
  sheets and to shots with no character or with the toolbox in view (EXPERIMENTS.md E22).
- **Letting a model pre-listen to the music.** It mostly repeated the brief I gave it and could not
  tell the candidates apart (EXPERIMENTS.md E14).

## 6. Ceiling work and what it taught me

Pending / **[ME]**: if time allows, the open-vs-paid comparison on one shot (docs/PAID_LANE.md,
benchmark protocol). Otherwise say what was designed in for it: the paid lane plugs in by config,
and the cache keys make a side-by-side comparison free to set up.

## 7. What I would build next

- The paid lane for the moving shots: the same Wan code on a rented GPU, at 720p and in bf16, with
  no T4 queue (docs/PAID_LANE.md).
- A small family web app: each relative records one phrase of Dad's, and it becomes a shot.
- **[ME]** Anything else.
