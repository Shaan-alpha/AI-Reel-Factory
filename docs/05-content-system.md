# Content System — Templates & Hooks

**Niche (LOCKED):** **Daily impact news/info explainers** — Indian & international
developments that could have a big impact on the world or India. **Style:** daily impact
explainer (*what happened → why it matters → impact*). **Lean:** soft/positive-impact —
science, tech, economy, breakthroughs, policy, world-changing-but-less-inflammatory stories;
mostly avoid partisan/communal politics.

**Rule:** Do NOT let the AI summarize the news like a wire service. YouTube's 2026
*Inauthentic Content* policy demonetizes mass-produced AI summaries. **Every reel must add
original analysis / perspective** ("why this matters", "what it means for you"). See
[08-news-niche-playbook.md](08-news-niche-playbook.md) — read it before building scripts.

---

## Templates

### Template N — News Impact Explainer ⭐ MVP DEFAULT (this niche)
`Hook (the development) → What actually happened (1–2 facts + source) → WHY IT MATTERS
(original analysis) → Impact on you/India/world → CTA`
This is the monetization-safe structure: the *analysis* is the original value, not the facts.
*Example:* "India just did something no country has tried → [what] → here's why it could
change [X] → what it means for you → follow for the stuff headlines skip."

### Template A — Hook → Problem → Solution → Twist → CTA
General-purpose teaching/value content (use for evergreen explainers).

### Template B — Controversial statement → Explanation → Examples → Conclusion
Drives comments/debate — use cautiously given the sensitivity lean.

### Template C — Story → Curiosity loop → Escalation → Reveal
Narrative; strong for "how this unfolded" backstories.

### Template D — Fast listicle → Rapid pacing → Quick dopamine
"3 things that happened today that actually matter" round-ups.

---

## Script constraints (YouTube Shorts, MVP)

- ≤ 60 seconds → roughly **130–150 spoken words**
- **First 3 seconds = the hook.** No throat-clearing.
- **Cite the source** in the script/caption ("according to …") — credibility + originality.
- **Add genuine analysis**, not just facts (the originality requirement — non-negotiable).
- Neutral, factual framing; no sensationalism or unverified claims.
- One development per reel. End with a CTA (follow / comment).
- Append `#Shorts` so YouTube classifies it correctly.
- **Word-by-word captions are burned in** (Module 7, faster-whisper).
- **AI-content disclosure** applied on upload (see playbook).

---

## Niche strategy — trend-driven by Claude (within the news lane)

`NICHE=impact-news` (set in `.env`). Claude (your Pro sub) **researches the day's
developments** via built-in web search and generates ideas *within this lane*. It should:

- Prefer **high-impact, under-covered angles** over headlines everyone already ran (originality).
- Pull from **reputable sources** and capture the source URL per idea.
- Apply the **soft/positive-impact lean** and the sensitivity filter (see playbook).
- Lean toward stories with a clear "why it matters to you/India/the world" angle.

**Sub-lanes that fit the lean:** science & space · technology & AI · economy & business ·
health & medicine · climate & energy · big policy/law shifts · global affairs (geopolitics,
neutral) · India growth/infrastructure/ISRO · breakthroughs & world-firsts.

---

## Hook Database (seed — news/impact tuned)

Store each hook with niche + performance so the learning loop (Phase 4) ranks/remixes winners.

- "India just did something no one expected…"
- "This could change [X] for the entire world…"
- "Nobody's talking about what just happened in…"
- "Most people missed this, but it's huge…"
- "This might be the biggest news of the week…"
- "Here's what the headlines didn't tell you…"
- "Why [event] matters way more than it sounds…"
- "Remember this day — here's why…"

**Schema** (`hook_performance`): `hook_text, niche, uses, avg_retention, avg_views`.
Claude's ideation reads top performers and produces fresh variants.

---

## Retention hacks (phase in during Phase 2+)

- **Agent Debate:** two TTS voices weigh "what this means" from two angles → audio tension.
- **Beat-sync cutting:** cut visuals on music beats → cheap footage feels premium.
- **1-frame Easter egg:** hide an emoji/word for one frame; caption "comment the timestamp" →
  forces rewatches → retention spikes.
- **Map/data B-roll:** maps, charts, data viz for impact stories (also more copyright-safe).
- **3-hook A/B test:** same story, 3 different first-3-seconds; post weeks apart.
- **Seed comment:** auto-pin a thought-provoking question on publish → early engagement.
