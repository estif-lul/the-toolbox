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
