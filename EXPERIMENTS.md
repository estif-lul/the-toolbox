# EXPERIMENTS — hypothesis → change → result

Each entry is written **when the experiment runs**, tied to evidence (run_ids in runs.jsonl,
cache keys, file paths, measured numbers). One variable changes at a time; the seed stays fixed
when comparing prompts. Target: at least 12 real entries. The planned backlog is in PLAN.md §13.

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

*(No experiments yet. Step 0 produced the baseline measurements in COSTS.md "Free tiers as
found" and the smoke results in `outputs/smoke/summary.json`.)*
