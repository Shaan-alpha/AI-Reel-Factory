# Template N — News Impact Explainer  ⭐ MVP default

**Structure:** `Hook (the development) → What actually happened (1–2 facts + source) →
WHY IT MATTERS (original analysis) → Impact on you/India/world → CTA`

This is the **monetization-safe** structure: the *analysis* is the original value, not the
facts (YouTube 2026 Inauthentic Content policy — see playbook §1).

## Constraints
- ≤ 60 seconds → ~110–130 spoken words.
- **First 3 seconds = the hook** — open a curiosity LOOP paid off only at the end. No throat-clearing.
- **Rewrite facts in your own words + cite** ("according to …"). Never copy phrasing.
- The core of the script is **original "why it matters" analysis**, not a summary.
- **Framing is max-hype** (curiosity/conflict/emotion — operator choice, proven by analytics); the
  **one hard line is accuracy** — never fabricate a fact/quote/number/event. Hype the story, don't invent it.
- **Title = viral, not search-SEO**: short, power-words, curiosity gap, conflict, ALL-CAPS on one word.
  Proven winners: "Oil Export Wars", "Messi's Nightmare Debut" (1000+ views) ≫ "X Explained" (flopped).
- One development per reel. End with a CTA (follow / comment).

## Prompt skeleton (filled by scriptwriter)
```
You are writing a ≤60s YouTube Short script for "But It Matters" (impact news/info explainers).
IDEA: {title}
HOOK: {hook}
ANGLE (the original take to develop): {angle}
SOURCES: {sources}

Write, in this order:
1. HOOK (≤3s): state the development so it stops the scroll.
2. WHAT HAPPENED: 1–2 key facts, in your OWN words, citing the source out loud.
3. WHY IT MATTERS: the original analysis — develop {angle}. This is the point of the video.
4. IMPACT: what it means for the viewer / India / the world.
5. CTA: follow for the stuff headlines skip / ask a question to drive comments.

Return JSON: { "script_body": "...", "caption": "...", "hashtags": ["...","#Shorts"] }
Caption must include the source link(s) + an AI-disclosure line. Title/caption should be
keyword-rich (SEO). Append #Shorts.
```

## Output
`{ script_body, caption, hashtags[] }` → written to the `scripts` table by Module 3.
