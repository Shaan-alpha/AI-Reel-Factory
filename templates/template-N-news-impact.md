# Template N — News Impact Explainer  ⭐ MVP default

**Structure:** `Disorienting Hook → Absurdity & What Happened (witty/sarcastic) → Retention Bridge & WHY IT MATTERS → Punchy Close & Loop CTA`

This is the **monetization-safe** structure: the *analysis* is the original value, not the
facts (YouTube 2026 Inauthentic Content policy — see playbook §1).

## Constraints
- **25–30 seconds** → ~65–75 spoken words.
- **First 2–3 seconds = disorienting hook** — open a curiosity LOOP paid off only at the end. No throat-clearing.
- **Rewrite facts in your own words + cite**. Never copy phrasing.
- **Tone = Witty, sarcastic, dry comedy** (Daily Show / Phil DeFranco style) roasting the absurdity of news, but keeping facts 100% true.
- **Retention Bridge** at 12–15s ("Here's why it actually matters...") to keep attention.
- **Title = honest curiosity gap**: short, gripping, true to the narration.
- Append #Shorts and AI disclosure line.

## Prompt skeleton (filled by scriptwriter)
```
You are writing a 25–30s YouTube Short script for "But It Matters" (impact news/info explainers).
IDEA: {title}
HOOK: {hook}
ANGLE (the original take to develop): {angle}
SOURCES: {sources}

Write, in this order:
1. DISORIENTING HOOK (first ~2s): surprising or absurd TRUE fact.
2. THE ABSURDITY: 2-3 crisp sentences on what happened with witty/sarcastic delivery.
3. RETENTION BRIDGE & WHY IT MATTERS: "Here's why it actually matters..." - the real consequence.
4. PUNCHY CLOSE: witty last line looping back to the hook + 2-3 word CTA.

Return JSON: { "title": "...", "script_body": "...", "caption": "...", "hashtags": ["...","#Shorts"], "tags": [...], "key_points": [...] }
Caption must include the source link(s) + an AI-disclosure line. Append #Shorts.
```

## Output
`{ title, script_body, caption, hashtags[], tags[], key_points[] }` → written to the `scripts` table by Module 3.
