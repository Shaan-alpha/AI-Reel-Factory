# Template D — Fast Listicle

**Structure:** `Fast listicle → rapid pacing → short captions → quick dopamine`
Best for "3 things that happened today that actually matter" round-ups.

> **Not wired.** A design note for a later phase: the scriptwriter runs Template N only and
> raises an error for any other. Wired as it stands, the 80-word cap (`SCRIPT_MAX_WORDS`)
> would cut the length below.

## Constraints
- ≤ 60s → ~130–150 words; 3–4 items max so each still gets a beat.
- **First 3 seconds = the hook** ("3 things today that actually matter →").
- Each item: one fact (own words + cite) + a one-line "why it matters".
- Truth over neutrality (CLAUDE.md rule 6): a verdict only where the evidence supports it. End
  with a CTA. Append `#Shorts`.

## Output
`{ script_body, caption, hashtags[] }`. As for Template N, code appends the "Sources:" block and
the AI-disclosure line to the caption.
