# Template N — News Impact Explainer  ⭐ the template in use

**Structure:** `Disorienting Hook → What Happened (own words, with a dry aside) → Retention Bridge & WHY IT MATTERS → Punchy Close that loops back (CTA optional)`

This is the **monetization-safe** structure: the *analysis* is the original value, not the
facts (YouTube 2026 Inauthentic Content policy — see playbook §1). It is the only template the
scriptwriter runs; the executable prompt is `_PROMPT_N` in `src/scriptwriter.py`. Keep the two
in sync.

## Constraints
- **25–30 seconds** → ~55–70 spoken words, never more than `SCRIPT_MAX_WORDS` (80); the prompt
  states the cap. Over it, an LLM tighten pass cuts to fit; dropping whole sentences is the
  backstop (the CTA goes first; the hook and the "why it matters" turn are kept).
- **First ~2 seconds = disorienting hook**: the single most surprising TRUE fact, opening a
  curiosity loop the close pays off. No throat-clearing.
- **Rewrite facts in your own words.** Never copy phrasing, and never copy the idea's angle.
- **Tone = witty, sarcastic, dry comedy** (Daily Show / Phil DeFranco style) roasting the
  absurdity of the news, with the facts kept 100% true. Roast situations and irony, never
  people.
- **Truth over neutrality:** say plainly what the evidence supports and who is responsible; the
  sharper the verdict, the more certain its facts. A separate fact check runs before voicing.
- **Retention bridge** straight after the hook ("Here's the catch...", "Wait, it gets
  weirder..."), then the payoff: "Here's why it actually matters...".
- **Delivery tags:** 1–3 per script; a tone tag on the "why it matters" turn is required (code
  adds `[serious]` there if the script has no tone tag).
- **Somber override** for deaths or serious harm: no sarcasm or jokes, only `[serious]` or
  `[pause]`, the payoff opened plainly with "Here's why it matters", and no hook punch-up.
- **Title = honest curiosity gap**: 40–55 characters, never more than 70 (code cuts longer
  titles), true to the narration. It is also the frame-1 banner.
- **Key points:** 2–3 on-screen cards, ≤ 4 words each.
- `#Shorts`, the "Sources:" block and the AI-disclosure line are added in code, never by the model.

## Prompt skeleton (filled by scriptwriter)
```
[today's date line]
You are the lead viral scriptwriter for "But It Matters": sharp 25-30 second YouTube Shorts with
a SARCASTIC, dryly funny, but DEAD-SERIOUS voice. Funny in the DELIVERY, never in the facts. The
hook is strong but TRUE: title and opening must sit honestly on what the video delivers.
IDEA: {title}
HOOK: {hook}
ANGLE (the take to develop): {angle}
SOURCES: {sources}

Write about 55-70 words, NEVER more than {max_words}:
1. DISORIENTING HOOK (first ~2s): the most surprising or absurd TRUE fact, with a dry edge.
2. THE ABSURDITY (2-3 sentences): what happened, in your own words, with a sarcastic aside
   (never changing a fact).
3. RETENTION BRIDGE & THE POINT (1-2 sentences): "Here's why it actually matters..." - the real
   consequence, said straight.
4. PUNCHY CLOSE: a witty last line that loops back to the hook (a 2-3 word CTA is optional).

Write for the ear; plain text, no markdown. 1-3 delivery tags ([pause], [sarcastic], [deadpan],
[dry], [serious], [curious], ...); a tone tag on the "why it matters" turn is required. Roast
situations, not people.
ACCURACY: verify the development happened; never invent product names, figures, dates, quotes
or events.
TRUTH OVER NEUTRALITY: no duty to be even-handed; say what the evidence supports and who is
responsible, but the sharper the verdict, the more certain its facts. An independent fact-check
runs on this script before it is voiced.

Also return: "title" (40-55 characters, never more than 70), "caption" (line 1: emoji hook;
line 2: why-it-matters summary + a comment question; NO links, no "Sources" line), "tags"
(12-15 search terms, no '#'), "key_points" (2-3 cards, <= 4 words each).
Return ONLY JSON: { "title", "script_body", "caption", "hashtags": [..., "#Shorts"], "tags", "key_points" }

+ EMPHASIS (ENABLE_HUMAN_ANGLE): develop the ANGLE in your own words; never copy its sentences.
+ TONE OVERRIDE (somber stories only): drop the sarcasm; only [serious] or [pause];
  open the payoff with "Here's why it matters".
```

## Output
`{ title, script_body, caption, hashtags[], tags[], key_points[] }`. Module 3 writes the title,
body, caption and hashtags to the `scripts` table (the fact-check verdict joins them in
`scripts.factcheck`); tags go into the upload metadata and key points become the on-screen cards.
