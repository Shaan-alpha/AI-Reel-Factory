# Content System — Templates & Hooks

**Niche (LOCKED):** **Daily impact news/info explainers** — Indian & international
developments that could have a big impact on the world or India. **Style:** daily impact
explainer (*what happened → why it matters → impact*). **Editorial policy:** truth over
neutrality (operator, 2026-07-27; CLAUDE.md rule 6): the channel may reach a verdict and name
who is responsible where the evidence supports it, and politics, government action and court
rulings are in scope. The old soft/positive lean is retired; the sensitivity filter is not
(docs/08 §5). **Voice:** dry, sarcastic wit about the absurdity of the news, facts kept
straight; a calm, serious read for stories about deaths or serious harm.

**Rule:** Do NOT let the AI summarize the news like a wire service. YouTube's 2026
*Inauthentic Content* policy demonetizes mass-produced AI summaries. **Every reel must add
original analysis / perspective** ("why this matters", "what it means for you"). See
[08-news-niche-playbook.md](08-news-niche-playbook.md) — read it before building scripts.

---

## Templates

### Template N — News Impact Explainer ⭐ the template in use
`Disorienting hook (one surprising true fact) → What happened (own words, with a dry aside) →
Retention bridge + WHY IT MATTERS (the original analysis) → Punchy close that loops back to the
hook (CTA optional)`
This is the monetization-safe structure: the *analysis* is the original value, not the facts.
It is the only template the scriptwriter runs. The prompt lives in `src/scriptwriter.py` and
mirrors [templates/template-N-news-impact.md](../templates/template-N-news-impact.md).
*Example:* "India just did something no country has tried → [what] → here's why it could
change [X] → what it means for you."

### Template A — Hook → Problem → Solution → Twist → CTA
General-purpose teaching/value content (use for evergreen explainers).

### Template B — Controversial statement → Explanation → Examples → Conclusion
Drives comments/debate. No template file; add one only if it clears the sensitivity filter
(docs/08 §5).

### Template C — Story → Curiosity loop → Escalation → Reveal
Narrative; strong for "how this unfolded" backstories.

### Template D — Fast listicle → Rapid pacing → Quick dopamine
"3 things that happened today that actually matter" round-ups.

> A, C and D are design notes in [templates/](../templates/), kept for a later phase. They are
> not wired: the scriptwriter supports Template N only and raises an error for any other.

---

## Script constraints (YouTube Shorts, Template N)

- **25–30 seconds → about 55–70 spoken words**, never more than `SCRIPT_MAX_WORDS` (80), and the
  prompt says so. Over the cap, an LLM **tighten pass** cuts to fit and keeps the hook and the
  "why it matters" turn; dropping whole sentences is the backstop (the CTA goes first, and no
  sentence is cut in half). Shorter = higher completion rate on Shorts.
- **First 2–3 seconds = the hook.** No throat-clearing. A hook judge scores the opening 1–10 and,
  below 7 (`HOOK_MIN_SCORE`), rewrites the title and opening; it is told not to change a fact.
- **Title ≤ 70 characters** (the prompt aims for 40–55; code cuts anything longer). The title is
  also the frame-1 banner, so it must be true to the video.
- **2–3 key-point cards** (≤ 4 words each) burned on screen. They are published claims, so the
  fact check covers them too.
- **Add genuine analysis**, not just facts (the originality requirement — non-negotiable).
- **Truth over neutrality:** a verdict only where the evidence supports it; the sharper the
  verdict, the more certain its facts. No sensationalism or unverified claims. Every finished
  script is fact-checked before it is voiced (docs/08 §5).
- **Delivery tags:** 1–3 per script (`[pause]`, `[sarcastic]`, `[serious]`, …). If a script
  comes back without a tone tag, code puts `[serious]` on the "why it matters" turn.
- **Somber tone** for deaths or serious harm: no sarcasm or jokes, only `[serious]`/`[pause]`, a
  plain "Here's why it matters", and no hook rewrite.
- One development per reel. A 2–3 word CTA is optional.
- **Sources are cited by code, not the model:** the description gets one "Sources:" block from
  the idea's fetched sources, and the reel shows "Source: <publisher>" for its first ~3 s.
- `#Shorts` and the **AI-disclosure** line are added in code (see playbook).
- **Karaoke captions are burned in** (Module 7): 3-word groups, each word lit as it is spoken.
  faster-whisper times the words; the text comes from the approved script.

---

## Niche strategy — how ideas are found (within the news lane)

`NICHE=impact-news` (the value stored on every idea row). Live ideation is
[`src/ideation_fallback.py`](../src/ideation_fallback.py), Gemini on Vertex, on every run:

1. **Pool:** Google News RSS (India edition front page plus the World, Business, Technology and
   Science sections; 24 stories, `NEWS_POOL_SIZE`), Google Trends RSS (India) as a supplementary
   signal, and the channel's best- and worst-viewed recent titles.
2. **Pick:** a story scout (Groq `openai/gpt-oss-120b` first) chooses N distinct stories a smart
   person would send to a friend (real stakes, money and power, genuine surprise, big human
   impact) and applies the sensitivity filter.
3. **Research and write:** each chosen story is checked against live Google Search in prose
   (`IDEATION_MODEL`, default `gemini-3.5-flash-lite,gemini-3.5-flash`), and the ideas are written
   from those notes (`GEMINI_MODEL`, default `gemini-3.8-flash`): an honest hook and a real "why it
   matters" angle, held to truth over neutrality.
4. **Source:** real sources are attached in code (grounded citations, then the feed's article
   link, then a Google News search); dead links are dropped, and so is an idea left with fewer
   than `MIN_SOURCES` (2). A story pitched in the last 10 days is not pitched again.

The Claude Routine in [routines/ideation.md](../routines/ideation.md) is optional and has never
run in production.

**Categories the scout spreads a run across:** world affairs · economy & business · science &
space · technology & AI · health · climate & energy · India infrastructure · government & policy
· sports · notable world events.

---

## Hook Database (seed — news/impact tuned)

A seed list for writing or judging hooks by hand; no code reads it.

- "India just did something no one expected…"
- "This could change [X] for the entire world…"
- "Nobody's talking about what just happened in…"
- "Most people missed this, but it's huge…"
- "This might be the biggest news of the week…"
- "Here's what the headlines didn't tell you…"
- "Why [event] matters way more than it sounds…"
- "Remember this day — here's why…"

**Schema** (`hook_performance`): `hook_text, niche, uses, avg_retention, avg_views`. The table
exists in Supabase, but nothing writes or reads it yet (Phase 4). The loop that does run is
title-based: `analytics.yml` snapshots every Short's views daily, and `db.top_performing_titles()`
(recent winners, at most two per story cluster) and `db.low_performing_titles()` go into the
ideation prompt as title styles to copy and to avoid.

---

## Retention hacks (phase in during Phase 2+; none built yet)

- **Agent Debate:** two TTS voices weigh "what this means" from two angles → audio tension.
- **Beat-sync cutting:** cut visuals on music beats → cheap footage feels premium.
- **1-frame Easter egg:** hide an emoji/word for one frame; caption "comment the timestamp" →
  forces rewatches → retention spikes.
- **Map/data B-roll:** maps, charts, data viz for impact stories (also more copyright-safe).
- **3-hook A/B test:** same story, 3 different first-3-seconds; post weeks apart.
- **Seed comment:** auto-pin a thought-provoking question on publish → early engagement.
