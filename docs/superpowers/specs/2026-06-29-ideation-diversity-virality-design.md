# Ideation quality: news-anchored, diverse & viral topics

**Date:** 2026-06-29
**Status:** Approved (design) — ready for implementation plan
**Scope:** `src/trends.py`, `src/ideation_fallback.py`, their tests. No DB schema, no workflow changes.

## Problem

The operator reports that when ideation generates multiple topics at once, the ideas are
**very similar to each other** and **not viral or trendy**.

### Diagnosis (evidence-backed)

Why topics come out similar:

1. **One LLM call generates the whole batch** ([ideation_fallback.py](../../../src/ideation_fallback.py)
   `_produce_ideas`) — a single call asked for ~18 ideas mode-collapses onto the 1–2 biggest
   stories and rephrases them.
2. **Dedup is exact-title only** (`_validate_and_clean`) — "ISRO launches X" and "What ISRO's X
   mission means" both survive (same story, different words).
3. **No diversity constraint** — the prompt lists categories but never *requires* spreading across
   distinct stories/categories or forbids two ideas about the same event.
4. **`generate_ideas` picks top-N by score** from that one clustered call, so picks stay clustered.

Why topics aren't viral/trendy:

5. **The trends feed is junk.** A live run of `trends.fetch_trending()` for India returned:
   *"weather winter storm warning", "shimla weather", "june 2026 calendar", "wimbledon",
   "us open badminton 2026", "germany vs paraguay", "snana purnima 2026"* — generic global search
   noise, not India impact-news — and the prompt tells the model to **prefer** ideas tied to these.
6. **The news feed is excellent.** A live run of `news.fetch_headlines()` returned 12 real, current,
   diverse stories (West Asia ceasefire, Modi in Seychelles, weakest monsoon in 17 years, Venezuela
   quake, …). This is the asset to anchor on.
7. **Grounding can silently fail** (Gemini free RPD was exhausted on 2026-06-10) → ungrounded
   fallback → the model's training-cutoff knowledge → generic/stale ideas.
8. **The prompt is weighted toward "honest/neutral/accurate"** (correct for rule 6) with no explicit
   "would someone *share* this?" virality bar.

## Decisions (from brainstorming)

- **Priority:** viral/share-worthy framing + trendiness/freshness. Anti-similarity is folded in
  because the chosen structure delivers it for free, but it is not over-engineered.
- **Viral ceiling:** *punchier but compliant.* Add a share test + stronger curiosity-gap hooks while
  keeping every hard guard from rule 6 intact (no fabrication, neutral framing, ≥2 real sources).
- **Approach:** A — news-anchored two-stage (chosen over a single richer call and over category
  fan-out). Quota is the binding constraint: Gemini free RPD is tight, so we cannot fan out many
  LLM calls per run without starving the accuracy-critical grounded research (rule 13).

## Design — news-anchored two-stage ideation

**Key property:** anchoring on the news feed makes freshness independent of Gemini grounding. If
grounding is quota-blocked, Stage 2 still expands *real current headlines*, so a grounding outage
degrades sourcing quality, not freshness.

### Component 1 — Fix the trends feed (`src/trends.py`)

- Add a best-effort **noise filter** that drops the observed junk:
  - weather (`weather`, `storm`, `monsoon` as a bare term, city-name weather lookups),
  - calendars / date lookups (`calendar`, `purnima`, festival-date and `YYYY` standalone lookups),
  - live-score matchups (`X vs Y`, `predictor`, standalone sports-tournament names).
- Filter is a tunable denylist of substrings/patterns; unmatched items pass through. Stays
  best-effort (rule 11) — an empty result just means ideation proceeds on news alone.
- The prompt (Component 4) **demotes** trends from "prefer ideas tied to these" to a supplementary
  flavor signal. News is the primary anchor.

### Component 2 — Two-stage generation (`src/ideation_fallback.py`)

Replace the single `_produce_ideas` call with two stages:

- **Stage 1 — Select (cheap; `llm.generate(prefer_groq=True)` to spare Gemini RPD):**
  one call takes the real headlines + filtered trends + past winners and **clusters same-story
  headlines, ranks by share-worthiness, and selects `target` *distinct* stories spread across
  categories.** Returns JSON `[{"story": "...", "category": "...", "why_shareworthy": "..."}]`.
  This is the anti-clustering mechanism — diversity is enforced structurally.
- **Stage 2 — Expand (grounded Gemini → ungrounded fallback, as today):**
  one call expands the selected distinct stories into the full idea JSON, verifying facts and citing
  real sources via grounding. The existing grounded→ungrounded JSON-mode fallback is preserved.

If Stage 1 fails or yields nothing usable, fall back to the **current single-call behavior**
(prompt the model directly for ideas) so ideation never dies (rule 11). If Stage 2's grounded call
fails, fall back to ungrounded expansion of the same selected stories.

### Component 3 — Virality bar + dedup backstop (validation in `_validate_and_clean`)

- New idea field **`share_score`** (0–1): the model's estimate of *"would someone send this to a
  friend?"* Coerced/clamped like `est_score`. Ranking (in `generate_ideas`, `seed_ideas`) becomes
  **`share_score`-primary, `est_score`-secondary**. `share_score` defaults to `est_score` when the
  model omits it (back-compat, and the single-call fallback path may not emit it).
- Keep exact-title dedup; add a lightweight **token-overlap backstop**: normalize titles to a set of
  significant lowercased tokens (drop stopwords/punctuation) and reject a candidate whose token
  overlap with an already-kept idea exceeds a threshold (e.g. Jaccard ≥ 0.6). No embeddings, no LLM
  call. Catches same-story near-duplicates that slip past Stage 1.

### Component 4 — Prompt rewrite (both stages)

- News = primary anchor; trends = supplementary flavor.
- One-idea-per-distinct-story; explicitly spread across categories; never two ideas on the same event.
- Punchy-but-compliant: add the **share test** and stronger curiosity-gap hook guidance, keeping
  **every** hard guard intact (no fabrication, neutral framing, ≥2 real source URLs — rule 6).
- Stage 2 prompt emits the existing schema **plus `share_score`**.

## Cost / quota (rule 13)

~2 LLM calls per ideation run (was ~1). Stage 1 → Groq (`prefer_groq`), Stage 2 → Gemini grounded.
Net Gemini RPD usage is roughly flat; the scarce grounded budget is reserved for Stage 2.

## Error handling (rules 11/14)

- Trends/news feeds already return `[]` on failure; unchanged.
- Stage 1 failure → single-call fallback (current behavior).
- Stage 2 grounded failure → ungrounded expansion of selected stories.
- Thin-digest guard (`_MIN_IDEAS`) and the idempotency guard in `run_fallback_ideation` are unchanged.

## Testing

Update [tests/test_ideation_fallback.py](../../../tests/test_ideation_fallback.py):

- Mock both stages: assert Stage 1 distinct-story selection feeds Stage 2 expansion.
- Assert `share_score`-primary ranking in `generate_ideas` / `seed_ideas`.
- Assert the token-overlap dedup backstop drops a same-story near-duplicate.
- Assert the Stage-1-failure → single-call fallback path.
- Assert the Stage-2 grounded-failure → ungrounded path (existing test, adapted).
- Keep the gated live test (`IDEATION_LIVE_TEST`).

Add a trends noise-filter unit test (new or in an existing trends test): junk in → filtered out,
real topics pass through.

## Out of scope (YAGNI)

- Category fan-out (Approach C) — multiplies LLM calls, quota risk.
- Embedding-based semantic dedup — token overlap is sufficient as a backstop.
- A temperature knob in `llm.py` — the two-stage structure delivers diversity without it.
- DB schema changes, workflow changes.

## Affected files

- `src/trends.py` — noise filter.
- `src/ideation_fallback.py` — two-stage `_produce_ideas`, `share_score`, dedup backstop, prompts.
- `tests/test_ideation_fallback.py` — updated/added cases.
- (trends test) — noise-filter case.
- `STATUS.md` / `CHANGELOG.md` — log the change (rule 1 / rule 18).
