# Walkthrough script (≤ 5 min)

A draft. I record it in my own words; the timings are targets.

**Before recording:**
- Terminal open in the repo; `runs.jsonl` and `storyboard.json` open in the editor.
- The 9:16 film ready to play.
- Pick the one narration line to edit live (s06 works: it is short, and only its own TTS request
  and its own Ken Burns length change).
- Check the TTS quota first: `make narration DRY_RUN=1`.

## 0:00–0:20 · The film
Play 15 s of `outputs/final/the_toolbox_9x16.mp4`, from s09 (the toolbox opens) to the phone call.
One sentence: "A 75-second film about my dad, who fixes everything himself, made by a pipeline of
free AI models."

## 0:20–1:30 · The architecture
- Show the Mermaid diagram in ARCHITECTURE.md.
- `storyboard.json` is the contract. Show one shot: its reason, image prompt, motion prompt,
  narration, and the choices I made (`keyframe_choice`). `make validate` checks it against the schema.
- Every stage writes outputs under a content-addressed key (`outputs/<stage>/manifest.json`), so
  only what changed is regenerated.
- `runs.jsonl` holds one line per call, cache hit, retry and fallback; `make costs` turns it into
  COSTS.md.

## 1:30–2:30 · One hard decision
Choose one:
- **Square masters for two aspect ratios.** Every picture is 1024² with the subject centred. The
  contact sheets draw the 9:16 and 16:9 crop boxes before anything is animated. Show
  `outputs/keyframes/s02/contact.png`.
- **Kaggle automation with a hash guard.** Inputs go up as a private dataset, and the kernel knows
  the hash of the jobs it was pushed with, so it refuses a stale dataset. Results come back as
  `results.jsonl` and become normal cache entries with GPU seconds.
- **The 10-requests-a-day TTS limit.** The whole narration is 3 requests: several lines per
  request, cut at the pauses, and every cut checked by hearing it back.

## 2:30–4:30 · Live: change one line, regenerate one shot
1. Edit the s06 narration text in `storyboard.json`.
2. Run `make film`.
3. Run `tail -n 30 runs.jsonl`: exactly **one** new `model_call` (TTS, s06), then `cache_hit` for
   everything else. The Ken Burns clip of s06 re-renders because its length changed. Then the
   final edit runs.
4. Play s06 in the new film.

## 4:30–5:00 · One thing learned
Example: "The model's defaults are not neutral: it drew the boy light-skinned until the text
insisted, every time. I check every image for that now." (EXPERIMENTS.md E21)
