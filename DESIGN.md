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

---

## 3. Story

`pipeline/script.py` (`make script`) sends this section, and only this section, to the text model
as the brief for an AI storyboard draft (see EXPERIMENTS.md E01).

### Logline
A son remembers how his Habesha father fixed everything at home himself, always starting with the
same calm words, *"እስኪ እንየው"* ("Let's look at it first"), until the day the son fixes something
alone and calls to tell him.

### Treatment
Morning light falls on a dented red toolbox. My dad never called anyone to fix anything: if it
could be done at home, he did it himself, and I was always one step behind him. Four memories
follow, each one a different kind of repair. I hold the torch while he lies under our old white
car. Wood shavings curl as he builds the rekebot we still serve coffee on. In a power cut, with
the jebena waiting on the charcoal stove, everyone says "call someone"; Dad picks up his tester and
says *"እስኪ እንየው"*, and the whole house lights up again. A leaking pipe, a wrench, patience, then
silence. Years later the roles turn: I tighten the bolt on the same car while he watches with his
arms folded and quotes the proverb about the egg that learns to walk. When I move out, he gives me
the toolbox. Now, when something breaks, I hear his voice. I fix the tap myself and call him. On
the other half of the screen, spanner in hand, he answers: *"ጎበዝ ልጄ"*, well done, my son.

### Beats (one picture each)
1. **The toolbox and the man who carries it** (s01–s02): the red toolbox in morning light, then Dad
   crossing the yard of the compound with it, the boy one step behind.
2. **Learning by helping** (s03–s07): four repairs, four tools: the torch under the car, the hand
   plane and the rekebot, the candle at the fuse box (*"እስኪ እንየው"*), the drip that stops.
3. **The turn** (s08): the teenager holds the spanner; Dad's arms are folded. The proverb
   *"ቀስ በቀስ እንቁላል በእግሩ ይሄዳል"* ("Slowly, slowly, the egg walks on its own legs") names it.
4. **The hand-over** (s09): the grown son opens the old toolbox in his own flat and hears Dad's
   *"እስኪ እንየው"* in his head.
5. **The call** (s10): a split screen, two phones, two tools. "Dad, I fixed it myself." *"ጎበዝ ልጄ"*.

### Characters
One fixed description per character is attached word for word to every image prompt that features
them (the exact text is in `storyboard.json`). Each has a **colour anchor** that survives ageing and
model drift: Dad is always in **faded navy-blue overalls** with a pencil behind his ear, I am always
in **mustard yellow**, and the toolbox is always **red**.

| id | Who | Appears in |
|---|---|---|
| `dad` | Dad in the memories: early forties, short curly hair greying at the temples, neat beard, navy overalls | s02, s03, s05, s08 (his hands in s04, s07) |
| `dad_now` | Dad today, about fifty: more grey, same overalls; generated from the `dad` reference | s10 |
| `me_child` | me at eight: round face, big curious eyes, oversized mustard T-shirt | s02, s03, s05, s06 |
| `me_teen` | me at fifteen: tall and lanky, mustard hoodie | s08 |
| `me_adult` | me in my mid-twenties: trimmed beard, mustard overshirt | s09, s10 |

Recurring objects and places are described once in the same way (`props`): the red toolbox (and
the same toolbox years later), the old white sedan, and the family home (cream walls,
corrugated-iron roof, sky-blue gate, eucalyptus trees, black water tank). Other family members are
only soft, unnamed background silhouettes (s05, s06).

### Visual approach
- **Cartoon, not realism.** A warm, hand-painted 2D cartoon look: soft golden light, gentle paper
  texture, rounded friendly shapes, an earthy palette of ochre, terracotta and eucalyptus green
  with sky-blue accents. Why cartoon: no real person's likeness is used (ETHICS.md); cartoon faces
  drift less visibly between shots than realistic ones; and a storybook look suits a memory told
  by a son. The style is described by its qualities, never by naming an artist or studio.
- **One prompt recipe for every image**, built in code so the wording never drifts:
  `{image_prompt}. {character descriptions}. {prop descriptions}. {composition}. Style: {style block}`.
  `image_prompt` holds only the subject, setting and shot size.
- **Square masters, two crops.** Keyframes are 1024×1024 with the subject centred and room on all
  sides, then cropped to 9:16 (phones, first) and 16:9 (YouTube, laptops) at assembly.
- **Light tells the time.** Morning gold for the opening, candlelight and night blue for the power
  cut, warm afternoon for the ending.
- **Where identity is hardest, show less face.** The woodwork and plumbing memories are close-ups of
  his hands (navy sleeves as the anchor); the car memory shows his legs under the car. Faces appear
  in medium and wide shots, where small drift is least visible.
- **Motion is gentle.** One small movement per shot (dust in the light, a flame, a nod) plus a slow
  camera move; Ken Burns on the keyframe is the fallback for every shot.

### Sound approach
- **Narration-led.** An English narrator (my voice in the story, a stock TTS voice, no cloning)
  carries the film; about 140 words over roughly 75 seconds, so there is room to breathe.
- **Dad speaks only Amharic**, three short lines in a second, deeper stock voice, each with an
  English subtitle. Fewer words make each one land, and the Amharic is what the family will
  recognise as *him*.
- **The recurring line returns as a memory.** In s09 the s05 recording of *"እስኪ እንየው"* is reused,
  quieter and with a soft reverb, as the voice in my head (no new model call).
- **A quiet score.** One instrumental cue in a nostalgic Ethiopian *tizita* feel (the word means
  memory, longing) with plucked krar, guitar and a light washint flute; ducked under the voice; it
  thins out for the silence after the leaking pipe (s07), and the theme returns warmer for the
  hand-over and the phone call.
- **Phone-ready mix.** Loudness normalised to −14 LUFS; subtitles burned in so the film works with
  the sound off.

### Shot reasons
Every shot exists for a reason; the exact text is the `reason` field of each shot in
`storyboard.json` (validation fails if one is missing). In short:

| Shot | Beat | Why it exists |
|---|---|---|
| s01 | motif | The hook: the red toolbox is the strongest colour in the film and carries the story from the first frame to the hand-over |
| s02 | place | Establishes the compound, Dad and the boy in one picture; the boy is literally one step behind |
| s03 | car | Memory 1: the boy as helper with the torch; the car returns in s08 to show the turn |
| s04 | woodwork | Memory 2: he makes, not only repairs; the rekebot ties his craft to the coffee ceremony |
| s05 | power cut | Memory 3: everyone would call someone, Dad looks first; introduces *"እስኪ እንየው"* |
| s06 | payoff | The lift: the house lights up and the boy's joy shows what his patience gives the family |
| s07 | plumbing | Memory 4: patience made visible; its silence is a breath before the turn |
| s08 | the turn | Years later the son works and Dad watches; the proverb names the growth |
| s09 | motif returns | The toolbox has changed hands; his line now lives in my head |
| s10 | ending | The call: we see Dad today, side by side with me; *"ጎበዝ ልጄ"* is the payoff |

---

## 4. User test 1 (radio cut)

**Why a radio cut first:** the story, the pace and Dad's lines can be tested before a single
picture exists, when changing them costs one TTS request per line instead of new keyframes and
GPU time.

**What they get:** `outputs/cuts/radio_cut.mp4` (75.7 s, built by `make radio` on 2026-11-25):
the full narration and Dad's three Amharic lines at their final timing, burned-in subtitles on a
black screen, a quiet code-generated placeholder pad instead of the music, and the AI label over
the last 3 s. Sent as a WhatsApp video (it plays inline on a phone, like the final film will).

**Who:** at least 3 people from the audience (family and friends), named here by relationship or
initials only. Dad hears it too: his reaction to his three lines is the follow-up promised in
ETHICS.md §2.

**The message sent with it:**
> This is a rough "radio" version of the short film I'm making about Dad: just the voice and
> subtitles for now, no pictures yet, and the music is a placeholder. It's 75 seconds. Could you
> watch it with the sound on and answer in a few words?
> 1. In one sentence, what is this film about?
> 2. Which moment stayed with you?
> 3. Was anything confusing, too slow or too fast?
> 4. How did you feel at the end?
> 5. Did anything sound wrong (a word, a name, a pause)? Did Dad's Amharic lines sound natural?
> 6. Does this feel like our family and home? What detail is missing or wrong?

**Status:** sent 2026-11-25 evening; replies by 2026-11-26 morning.

**Result (my summary, 2026-11-26 ~10:00 EAT):** the people I shared it with thought it was OK as
it is. Nobody asked for a change to the story, the pace or Dad's lines, so nothing in the
narration changed and no TTS request was spent. The individual answers were not collected
question by question; if I paste any of them later they go in the table below, verbatim.

| Who (relationship) | Date / how | Q1 About | Q2 Moment | Q3 Confusing / pace | Q4 Feeling at the end | Q5 Sound / Amharic | Q6 Our family? |
|---|---|---|---|---|---|---|---|
| Family and friends (summarised by me) | 2026-11-25/26, WhatsApp | — | — | no problem raised | — | no problem raised | no problem raised |

**Insights:** no pattern of confusion; the story and the 75 s length hold up as a radio piece. Test 1
is thin evidence (no per-question answers), so user test 2 (near-final cut, Step 5) asks the same
questions, records each answer, and checks what this test could not: the pictures, the
consistency of the characters, and whether the proverb's subtitle lands.

**Changes decided:** none to the story or the narration. (The picture changes made since come from
my own review of the images, not from this test: FAILURES.md F12, F13, F15.)

Things I'm listening for in the answers, from building it: whether "Dad, I fixed it myself" reads
clearly (the automatic check, `make narration-check`, hears "That I fixed it myself"), whether the proverb's
subtitle is understood by the non-Amharic speakers, and whether 75 s feels long on a phone.

## 5. User test 2 (near-final cut)

**What they get:** `outputs/final/the_toolbox_9x16.mp4`: the near-final film as people will see it
on a phone (pictures, moving shots where Wan produced a good clip, the chosen score, burned-in
subtitles, the AI end card). Sent as a WhatsApp video.

**Who:** at least 3 people, ideally at least one who heard the radio cut (named by relationship
only), and Dad if he wants to see it.

**The message sent with it:**
> This is the nearly finished version of the short film about Dad (about 75 seconds, made with AI).
> Could you watch it with the sound on and answer in a few words?
> 1. In one sentence, what is this film about?
> 2. Which moment stayed with you?
> 3. Was anything confusing, too slow or too fast?
> 4. How did you feel at the end?
> 5. Did the characters feel like the same people all the way through (Dad, and the boy as he grows up)?
> 6. Could you read the subtitles easily? Did anything sound wrong?
> 7. Does it feel like our family and home? What detail is missing or wrong?

**What I am checking from my own review**, beyond test 1:
- Whether Dad still reads as Dad in s08, where he is not in his overalls (FAILURES F13).
- Whether the 9:16 split screen at the end reads as a phone call.
- Whether the moving shots feel alive or uncanny.

**Answers** (verbatim, pasted as they arrive):

| Who (relationship) | Date / how | Q1 About | Q2 Moment | Q3 Confusing / pace | Q4 Feeling at the end | Q5 Same people? | Q6 Subtitles / sound | Q7 Our family? |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |

**Insights:** *(patterns across answers)*

**Changes decided** (each goes into `storyboard.json` in a commit that names this test; `make film`
then regenerates only what changed, and runs.jsonl shows it):
- *(to fill)*
