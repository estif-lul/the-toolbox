# DESIGN — "The Toolbox"

This file records who the film is for and what it should do, written **before anything was
generated** (see the git history: this file is in the first commit, ahead of any model call).
Later sections record the user tests and the changes they caused.

---

## 1. Brief

### Audience
Friends and family, almost all Habesha (Ethiopian): parents' generation, cousins, aunts and uncles,
and friends who know my dad. Some live in Ethiopia, some in the diaspora.

### Where they watch
On phones. The film is shared in family WhatsApp and Telegram groups and posted on social media
(Instagram / TikTok / YouTube Shorts). That means:
- **Vertical first** (9:16), with a horizontal (16:9) version for YouTube and laptops.
- Often watched **with low or no sound** (in a taxi, at work, in a busy house), so the story must
  survive on **burned-in subtitles** and pictures alone.
- Small screens: one clear subject per shot, centred, no small details that carry meaning.
- Short attention in a feed: the first 3 seconds must show something worth staying for (the red toolbox).

### Intended feeling at the end
**Pride and warmth.** They recognise him ("that is exactly him"), and they see that his skills, and
his way of facing a problem, now live in me. The last moment should feel like a smile, not tears.

### What they should understand
Dad never called anyone to fix anything; he taught me by doing it with me; and now I do it myself.
The phrase *"እስኪ እንየው"* ("Let's look at it first") is how he faces every problem, and it is now mine.

### How might we…
> How might we help our family and friends feel, in about 75 seconds on a phone, that Dad's patient
> "let's look at it first" way of fixing things has been handed down, so they feel proud of him and
> see him in me?

### Personas
1. **Aunt Tsehay (persona, ~55), Addis Ababa.** Watches on an Android phone in the family WhatsApp
   group, sound low, often while cooking. Reads the subtitles more than she listens. She knows Dad
   well and will notice if the house, the coffee ceremony or the way he talks feel wrong. She will
   forward the film to the whole group if it makes her proud of him.
   *Needs:* large, high-contrast subtitles; familiar home details; an ending she can react to with a ❤️.
2. **Cousin Nahom (persona, ~22), diaspora.** Scrolls Instagram and TikTok with sound on, swipes
   away anything slow in the first seconds. Understands spoken Amharic but reads English faster.
   *Needs:* a strong first image, short shots, a clear payoff, Amharic lines that sound natural
   (with English subtitles), and nothing that looks like a generic AI video.

(These are made-up but realistic people who stand for the audience; they are not real relatives.)

### Constraints
- **Deadline:** Thursday 26 Nov 2026, 23:59 EAT (internal target 22:30).
- **Length:** 60–90 s, plus a visible "Made with AI" end card.
- **Cost:** free tiers only (Gemini API, Cloudflare Workers AI, Kaggle T4 GPUs); measured in COSTS.md.
- **Cartoon only:** no photo, likeness or voice of any real person is used as input or reproduced
  (see ETHICS.md). Dad and I appear as fictional cartoon characters.
- **Privacy:** no real names (beyond "Dad"), addresses, plates or workplaces in prompts sent to free endpoints.
- **Language:** English narration (stock TTS voice); Dad speaks 3 short Amharic lines with English subtitles.
- **Reproducible:** one command (`make film`) rebuilds the film from `storyboard.json`.

---

## 2. Ideation

Four storylines were sketched before choosing. All four are about the same truth: Dad does
everything himself (car, woodwork, electricity, plumbing) and I learned it from him.

| | Storyline | Shape | Strength | Weakness |
|---|---|---|---|---|
| **A** | **The Toolbox** | Each tool in Dad's red toolbox opens one memory (car, woodwork, electricity, plumbing); at the end the toolbox is handed to me. | One strong visual **motif** that is easy to keep consistent across shots (an object, not a face); a natural ending (the hand-over). | On its own it is a list of memories; it needs a line that ties them together. |
| B | Pass Me the… | Told through what he asked me to hand him ("pass me the 10 mm spanner…"); I grow from the boy holding the torch into the one holding the spanner. | Very personal, the child's point of view; good for sound. | Relies on many small tool close-ups and hands, a known weak spot for image models; harder to read without sound. |
| C | The House His Hands Built | A tour of the family home: everything in it that he built or repaired. | Strong sense of place; the house is a single consistent setting. | A tour has no turn; Dad becomes a background figure; risks revealing too much private detail about the real house. |
| **D** | **Let's Look at It First** | Structured around his phrase *"እስኪ እንየው"*: every problem (blackout, leak, broken car) is met with the same calm line, until I say it myself. | A verbal **motif** that carries the emotion and works for an Amharic-speaking audience; gives the ending its meaning. | No visual anchor; the phrase alone can feel repetitive. |

### Choice: A + D
- **A gives the picture, D gives the voice.** The red toolbox is the visual thread (it opens the
  film, returns in s09 and closes the story); *"እስኪ እንየው"* is the spoken thread (first heard in the
  power cut, echoed when I open the toolbox myself).
- **It suits the audience:** a family audience recognises the phrase instantly, and the toolbox
  reads clearly on a phone, even without sound.
- **It suits the tools:** an object motif is far easier to keep consistent than a face; the memories
  can lean on hands, objects and medium/wide shots where cartoon identity drift is least visible.
- **It has a turn and an ending:** he stops fixing things *for* me and starts fixing them *with* me
  (the proverb *"ቀስ በቀስ እንቁላል በእግሩ ይሄዳል"*), then I fix something alone and call him:
  "Dad, I fixed it myself." He answers *"ጎበዝ ልጄ"*.
- B's best idea (the boy holding the torch) survives as shot s03; C's sense of place survives as the
  compound in s02 and the house lighting up in s06.

The logline, treatment, beat list and characters are added to this file next, and every shot's
reason lives in `storyboard.json`.

---

## 3. User test 1 (radio cut)
*To be filled in Step 2.*

## 4. User test 2 (near-final cut)
*To be filled in Step 5.*
