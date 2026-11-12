# Template N — News Impact Explainer  ⭐ the template in use

**Structure:** `Sentence one: the newest or most extreme true fact, with the Indian stake → one of three structures → the payoff: what changes for a person in India`

This is the **monetization-safe** structure: the *analysis* is the original value, not the
facts (YouTube 2026 Inauthentic Content policy — see playbook §1). It is the only template the
scriptwriter runs; the executable prompt is `_PROMPT_N` in `src/scriptwriter.py`. Keep the two
in sync. Design: [section 9 of the AI-video reels design](../docs/superpowers/specs/2026-11-10-ai-video-reels-design.md).

## Constraints
- **The viewer:** Indians aged about 18-34 on a phone, at home in Hindi and English, who care
  about money, jobs, exams, safety, gadgets and the country's standing.
- **The voice:** a clear, curious, confident explainer. No sarcasm, no mockery, no jokes at
  anyone's expense (the sarcastic voice was retired on 2026-11-12).
- **Sentence one** states the newest or most extreme true fact, with its subject and the Indian
  stake in its first clause; never a wind-up word, a date, a day or a greeting. Checked in code
  on every script (`opening_problem`).
- **Three structures** after sentence one, chosen per idea (a somber story always takes the
  first): what happened (how, why it matters, what is scheduled next); the number (what it
  measures, what it compares with, why it matters); the belief (the belief it overturns, only
  when a source records it, the evidence, why it matters).
- **The payoff** says what changes for a person in India (a price, a rule, a date, a risk, a
  job), from the sources; with no Indian stake, what changes for anyone. The writer marks it with
  `payoff_index`.
- **Length** in seconds: about 27 seconds (about 59 words), never more than 33 seconds (about 73
  words). Sentences the writer marks `optional` are cut first, never sentence one or the payoff.
- **Rewrite facts in your own words.** Never copy phrasing, and never copy the idea's angle. The
  prompt describes moves; it carries no example phrases to copy.
- **Truth over neutrality:** say plainly what the evidence supports and who is responsible; the
  sharper the verdict, the more certain its facts. A separate fact check runs before voicing.
- **Delivery tags:** at most two, from `[pause]`, `[serious]` and `[curious]`; code adds
  `[serious]` on the payoff if the script has no tone tag.
- **Somber note** for deaths or serious harm: calm and respectful, only `[serious]` or `[pause]`,
  the payoff still required and still marked, and no hook punch-up.
- **Title:** English, at most 7 words and 44 characters, the searchable name first, stating the
  claim the reel delivers. It is also the frame-1 banner.
- **Caption:** line 1 restates the claim with its main keyword; line 2 is one sentence on why it
  matters. No links and no question to the viewer.
- **Hashtags:** at most two, naming the story's subject or event. **Tags:** at most six (names and
  alternate spellings, Hindi spellings allowed). **Key points:** 2–3 on-screen cards, ≤ 4 words
  each.
- The "Sources:" block and the AI-disclosure line are added in code, never by the model.

## Prompt skeleton (filled by scriptwriter)
```
[today's date line]
You write the narration for "But It Matters", 25-35 second explainer Shorts for Indian viewers:
[the viewer]. A clear, curious, confident explainer: no sarcasm, no mockery, no jokes at anyone's
expense. Title and opening sit honestly on what the video delivers.
IDEA: {title}
HOOK: {hook}
ANGLE (the take to develop): {angle}
SOURCES: {sources}

SENTENCE ONE: the newest or most extreme true fact, subject and Indian stake in its first clause.
THEN THIS STRUCTURE: {structure}
THE PAYOFF: what changes for a person in India, from the sources; else what changes for anyone.
LENGTH: about {target_seconds} seconds, about {target_words} words, never more than {max_words}.
WRITE FOR THE EAR: plain text, "..." for a beat, at most two tags from [pause], [serious], [curious].
ACCURACY: verify the development happened; never invent product names, figures, dates, quotes
or events.
TRUTH OVER NEUTRALITY: no duty to be even-handed; say what the evidence supports and who is
responsible, but the sharper the verdict, the more certain its facts. An independent fact-check
runs on this script before it is voiced.

Also return: "title" (≤ 7 words, ≤ 44 characters), "caption" (two lines, no links, no question),
"hashtags" (≤ 2), "tags" (≤ 6), "key_points" (2-3 cards), "payoff_index", "optional", "structure".
Return ONLY JSON.

+ EMPHASIS (ENABLE_HUMAN_ANGLE): develop the ANGLE in your own words; never copy its sentences.
+ TONE (somber stories only): calm and respectful; only [serious] or [pause]; the payoff still
  required and marked.
```

## Output
`{ title, script_body, caption, hashtags[], tags[], key_points[], payoff_index, optional[], structure }`.
Module 3 writes the title, body, caption and hashtags to the `scripts` table (the fact-check
verdict joins them in `scripts.factcheck`); tags go into the upload metadata and key points become
the on-screen cards.
