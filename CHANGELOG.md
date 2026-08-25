# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); this project uses
[Semantic Versioning](https://semver.org/). Phase milestones are tagged
(`v0.1.0` = Phase-1 MVP done).

## [Unreleased] — The Groq fallback had been dead, and nothing noticed

### Fixed
- **`llama-3.3-70b-versatile` no longer exists on Groq** — every call returned 404
  `model_not_found`. Rule 11's mandatory chain therefore had a **dead second link**: the moment
  Gemini hit its free cap, `llm.generate` failed outright instead of failing over. Found live on
  2026-08-25 while checking something unrelated.
- **Why the suite never caught it:** every Groq test mocks `_gen_groq`, so they verify the
  failover *logic* and say nothing about whether the configured model is real. 366 green tests
  and a completely broken fallback are not contradictory. Ironically the file already had a test
  whose docstring warns that Gemini failures get "HIDDEN by the Groq failover" — the failover was
  itself the thing hiding.
- **This was not academic.** The Gemini free tier is **20 requests/day per model**, and one reel
  spends several LLM calls. Above roughly two reels a day the pipeline was running with no
  safety net at all, and would simply stop.
- **Now `openai/gpt-oss-120b`** — the most capable model Groq still serves that handles both
  plain and `json_object` mode, which the scriptwriter and keyword extraction both require.
  `qwen/qwen3.6-27b` was rejected: it answers plain prompts but 400s on JSON and leaks `<think>`
  reasoning into its output.
- **`test_configured_groq_model_actually_exists`** now calls the live API in both modes (skips
  without a key), so the next retirement fails a test instead of a production run. Confirmed
  failing against the old default.
- Verified end to end in the real failure mode: with Gemini 429ing, `generate()` returns `OK` and
  `generate(json=True)` returns valid JSON via Groq. **366 pass, 4 skipped.**

## [Unreleased] — Stop recycling B-roll, and keep one narrator

### Fixed
- **`visuals` sized its B-roll off a hardcoded 6.0s cut while `assembly` cut at `CLIP_SECONDS`
  (~3.5s).** A 30s reel therefore asked for 11 slices, got 6 images, and the slicer filled the
  gap by replaying earlier shots. `_ordered_clips` normally softens a repeat by advancing the
  start offset within the clip — but a Ken Burns clip is a pan over ONE still, so every offset
  of it is the same picture and the repeat is plainly visible. Gemini's audit of the newest
  published Short named that loop as the predicted swipe-away point (0:18), listing three shots
  replayed verbatim in the second half.
- **`assembly.slice_count(duration)` is now public and is the single source of truth** for the
  cut count, transitions included; `visuals._fetch_image_broll` sizes itself from it. Two modules
  deriving the same number from different constants is exactly the drift rule 7 exists to stop.
- Measured effect — repeats per reel: **18s 3→0 · 25s 3→0 · 30s 5→0 · 35s 5→0.** The
  `_MAX_IMG_CLIPS` cap (12) still bounds image-generation cost (rule 13), covered by a test.
- **The Chirp fallback voice was `en-IN-Chirp3-HD-Kore` (female) against a male Gemini primary
  (Zubenelgenubi)**, so a double Gemini 503 — and 3.1-flash-tts 503s often — silently changed the
  channel's narrator mid-catalogue. Now `en-IN-Chirp3-HD-Zubenelgenubi`: the same voice all the
  way down the chain. Changed in the repo variable, local `.env`, and documented in `.env.example`
  so it doesn't get casually reverted.
- +7 tests (`assembly.slice_count` contract, per-duration B-roll coverage, cost cap). **364 pass,
  4 skipped.**

## [Unreleased] — The "what wins" loop was learning from 3 videos out of 72

### Fixed
- **`db.top_performing_titles` ranked analytics *snapshots* instead of videos.** `analytics` is a
  time series — `collect_stats()` appends one row per published post per run — so ordering raw
  rows by views handed the top slots to a single breakout Short's own daily history. Measured on
  the live DB (2026-08-25): **72 posts, 3,454 snapshots, the top-24 window covered 3 distinct
  videos**, so `top_performing_titles(6)` returned **3** winners and ideation learned its
  "what works" style from a 3-video sample of a 72-video channel.
- The bug was **progressive**: every extra day added another snapshot per post while the window
  stayed fixed at `limit * 4`, so coverage decayed as the channel grew — quietly, since a short
  list is indistinguishable from a young channel.
- **Fix: collapse to one row per post first (its newest snapshot — for a monotonically rising
  view count that is also its highest), then rank.** The window now scales with the published-post
  count instead of the requested limit, so a full snapshot pass always fits.
- Verified against the live DB: **3 → 6 winners** for the same call.
- +5 tests in `tests/test_db_top_performers.py`, run with a fake PostgREST client so they need no
  creds. The fake honours `.order()`, since ordering by `views` vs `id` *is* the bug. Confirmed
  they fail against the pre-fix implementation. **357 pass, 4 skipped.**

## [Unreleased] — New channel voice model, chosen by ear

### Changed
- **`GEMINI_TTS_MODEL` now defaults to `gemini-3.1-flash-tts-preview`** (was
  `gemini-2.5-flash-preview-tts`), in code and both workflows. The operator A/B'd all three
  renders on an identical script and ranked **3.1-flash > 2.5-flash > Chirp**. Free on input and
  output; the voice stays **Zubenelgenubi**.
- Promoting a *preview* model to default is safe here for one specific reason: **the preference
  order is the same as the fallback order.** A 503 drops to `gemini-2.5-flash-preview-tts` with
  the same voice — the second-favourite sound — and only then to Chirp. The in-engine fallback
  added earlier stops being a nicety and becomes load-bearing.
- ⚠️ The model is genuinely flaky — 503 "high demand" on 3 of 4 attempts on 2026-08-07 — so expect
  some reels voiced by 2.5-flash. Both are free, so this costs consistency, not money.
- A test now pins that the fallback is a **different** model from the primary; otherwise a 503
  would re-ask the same unavailable model and burn two of a 10/day free budget.
- +1 test (352 pass, 4 skipped).

## [Unreleased] — Guarantee the payoff line is read like it matters

### Added
- **`scriptwriter._ensure_delivery_tag` — a floor of one delivery tag**, `[serious]` on the "why
  it matters" turn, plus a prompt that now requires it. The prompt previously said "AT MOST 3 …
  fewer is better", which permits zero: measured against the last 5 produced scripts, **2 shipped
  with no delivery tags at all**. The payoff line is both the emotional turn and the originality
  signal carrying the monetization gate (docs/08 §1), and it is the line most damaged by being
  read in the same dry register as the joke before it. A prompt asks; a guard makes it true.
- `ENABLE_TAG_FLOOR` (default true), wired into `.env.example` and both workflows.
- **`voice.has_style_tag()` is now public** so the scriptwriter asks the voice module rather than
  keeping a second copy of the allow-list — two lists drifting is exactly how `[curious]` came to
  be emitted but silently stripped.
- **A loud warning when a script has no "why it matters" turn at all.** Found live on script 158,
  where it shipped because nothing checked. That is an originality problem, not a style nit: a
  script without the turn is a bare summary, which is what YouTube's inauthentic-content policy
  demotes and what the monetization gate gates (docs/08 §1). Warns rather than blocks — accuracy
  already has a hard gate, and stacking a second blocking gate on a *soft* quality judgement would
  cost reels for something a human should eyeball (rule 14).
- +10 tests (351 pass, 4 skipped).

### Notes
- Deliberately fail-soft: if the payoff sentence cannot be located confidently the body is
  returned **unchanged**, because a tag in the wrong sentence is worse than no tag. Replayed over
  the last 10 real scripts — 8 already-tagged untouched, 1 fixed with the tag landing exactly on
  the bridge, 1 left alone. No regressions.
- The floor runs **after** the word cap, so truncation cannot cut the tag back off; tags are not
  spoken words, so it cannot push a script over the 25–30s budget.

## [Unreleased] — Wider expressive range, and a voice that survives a preview-model blip

### Added
- **Expressive tag vocabulary widened 7 → 12** against Google's documented audio-tag list, which
  both `gemini-2.5-flash-preview-tts` and `gemini-3.1-flash-tts-preview` accept — so this lands on
  the engine already in production. New: `[serious]` (the "why it matters" turn — the one that
  tells the audience you mean it), `[curious]`, `[whispers]`, `[tired]`, `[mischievously]`.
  The scriptwriter prompt now teaches each one's purpose, with the 3-tag cap unchanged.
- **Deliberate exclusions, now pinned by tests** so an accidental re-widening fails loudly:
  `[excited]`/`[amazed]`/`[giggles]` fight the deadpan register, and `[crying]`/`[panicked]`/
  `[trembling]`/`[gasp]`/`[shouting]` are melodrama over real events — the road to the tragedy
  exploitation rule 6 forbids. All are documented and would work; they are excluded editorially.
- **`tools/compare_voices.py` now renders `gemini-3.1-flash-tts-preview` too**, and its sample
  script exercises `[curious]` → `[sarcastic]` → `[serious]` so the A/B judges the tags, not just
  the timbre.

### Fixed
- **A transient TTS blip no longer costs the channel its voice.** `Zubenelgenubi` exists only on
  the Gemini engine, so a 503 used to fall straight through to Chirp and silently change how that
  reel sounded. `_synthesize_gemini` now retries once on the stable free model with the same voice
  before leaving the engine. Not hypothetical: `gemini-3.1-flash-tts-preview` returned 503 "high
  demand" on **three** attempts across ~40 minutes on 2026-08-07.
- Quota errors are explicitly **not** transient — a 429 shares the same daily reset across models,
  so retrying only burns the reel's time before the engine chain can do its job (rules 11, 13).
- +19 tests (341 pass, 4 skipped).

## [Unreleased] — Gemini 3 for scripts; grounding pinned where it is still free

### Changed
- **Ungrounded text generation moved to `gemini-3.6-flash`** (was `gemini-2.5-flash`). Free-tier
  quota is metered **per model**, and measured live on this account 2026-08-07: `3.6-flash`,
  `3.5-flash`, `3.5-flash-lite`, `3.1-flash-lite` and `3-flash-preview` all answered normally
  while `gemini-2.5-flash` was returning `limit: 20, model: gemini-2.5-flash`. So this is both a
  better model for scripts/hooks **and** a second daily budget that no longer competes with
  grounding.
- **Grounded research stays pinned to `gemini-2.5-flash` via a new `GEMINI_GROUNDED_MODEL` knob.**
  Google Search grounding 429s on **every** 3.x model with an empty quota-violation list — the
  signature of no free allowance — while 2.5-flash 429s with an explicit `limit: 20`, a real
  budget merely spent. It is still the only model with free grounded search.

### Fixed
- **Footgun: one knob drove both paths.** `_gen_gemini_grounded` defaulted to `GEMINI_MODEL`, and
  `.env.example` advised *"bump if free-tier RPD gets tight"* — doing so would have silently
  killed grounded ideation, the grounded scriptwriter **and** the fact-check gate at once. The two
  are now separate settings, wired into `.env.example` and both workflows.
- **`thinking_budget=0` is rejected by Gemini 3.x** (400 INVALID_ARGUMENT, verified live on
  `gemini-3.6-flash`); it was replaced by `thinking_level`, whose floor is `MINIMAL`. New
  `llm._thinking_cfg(model)` picks the right field per generation. This mattered more than it
  looks: the Groq failover **swallowed** the 400, so every Gemini call would have quietly become
  a Groq call while still appearing to work.
- +3 tests (324 pass, 4 skipped).

## [Unreleased] — Fact-check gate: stop fabrication, not imprecision

### Changed
- **The fact-check gate now grades findings by severity and blocks only on fabrication.**
  Operator report: it was failing most content ideas over "very minute differences". Root cause was
  the gate being all-or-nothing on top of a prompt that actively encouraged nitpicking — it listed
  "the real figure, date or name differs" and "overstates its scale or certainty" as failures, and
  declared *"absence of evidence is failure, not a pass"*, so any true story one search pass
  happened not to surface was killed. A gate that stops everything protects nothing; it just stops
  the channel.
  - **Blocking** (reel dies, idea `rejected`): the event/ruling didn't happen; a named party
    credited or blamed for something they didn't do; an invented quote, law, product, report or
    statistic; a number wrong by an order of magnitude, the wrong direction, or >~25%; a blame
    claim **no** source supports.
  - **Minor** (logged loudly, reel ships): rounding; a figure that differs because sources count
    it differently; a date off by a few days; wording, emphasis or over-confidence; a claim
    nothing contradicts but this pass couldn't confirm; sources disagreeing with each other.
  - **Contradiction blocks; non-confirmation does not** — one grounded pass missing a real story
    is routine, and "I couldn't find it" is not evidence that it's false.
  - **Two sources disagreeing is not proof the script is wrong** (the operator's own reasoning):
    both can be wrong, both can be right, or they can be measuring different things. Only the
    *weight* of evidence blocks.
  - This loosens **precision, not the anti-fabrication spine**. Rule 6's trade — the sharper the
    verdict, the more certain its facts must be — is about invented facts and misplaced blame,
    and those still block.
- **Grading now outranks the verdict word in both directions.** "pass" with a blocking finding
  still blocks (a model marking its own homework is what the gate exists to catch); "fail" with
  only nitpicks now ships. A `fail` naming *nothing* still blocks — there is nothing to grade.

### Added
- **`FACTCHECK_SEVERITY`** (`critical` default | `any`) — `any` restores the old
  block-on-every-discrepancy behaviour. Wired into `.env.example` and both workflows.
- `verify()` returns a `minor` list alongside `unsupported` (now the *blocking* findings), and
  `production.produce_one` logs waived issues per reel — a rising count means the scriptwriter is
  drifting, which is where to fix it rather than by re-tightening the gate.
- +9 fact-check tests covering the split, the escape hatch, and malformed checker output.

### Fixed
- **Fail-open in the findings parser, caught by a new test:** a checker returning a lone finding as
  a bare object (`"blocking": {...}`, not a list) had it silently dropped — i.e. a real fabrication
  would have shipped. Bare strings and bare objects are both wrapped now.

## [Unreleased] — Truth over neutrality + a fact-check gate

### Changed
- **Editorial policy: truth over neutrality** (operator decision). The `soft-positive` lean and
  the "strictly neutral / never take political sides" rule are retired — the channel may reach a
  verdict and name who is responsible. Politics, government action and court rulings are fully in
  scope. `NICHE_LEAN` is deleted; it was read by nothing.
- **CLAUDE.md rule 6 and docs/08 §5 rewritten** to match, rather than leaving the code
  contradicting the written contract (rule 1).
- The sensitivity filter is unchanged: communal/religious incitement, inflaming violence,
  rumour-as-fact, deepfakes, graphic tragedy exploitation and medical/financial advice stated as
  fact remain excluded. This widened what may be *said*, not what may be *targeted*.

### Added
- **`src/factcheck.py` — an independent, adversarial verification gate.** Re-checks the FINISHED
  script against live grounded search before any render, which is the cheapest place to abort. An
  unsupported claim blocks the reel and marks the idea `rejected` so it cannot retry-loop.
  "Cannot verify" counts as unsupported. Tone is explicitly out of scope: a harsh verdict the
  evidence supports passes, a mild claim it cannot source does not. Separate from the scriptwriter
  by design — grounding its own output was a model marking its own homework.
- The claim list outranks the verdict word: a checker that lists problems then says "pass" is the
  exact failure this gate exists to catch.
- `ENABLE_FACT_CHECK` (default true) and `FACTCHECK_STRICT` (default false). Grounded search
  shares one ~20/day free-tier bucket with ideation and the scriptwriter, so the gate can be
  unable to run; strict mode blocks in that case instead of shipping unverified.

### Fixed
- `tests/test_production.py` had begun making **real network calls** once the gate was wired, and
  passed for the wrong reason (a 429 took the fail-open path). Now mocked — 4.69s to 0.57s.
- **311 tests pass, 4 skipped** (was 290, 3).

## [Unreleased] — Expressive narration

### Changed
- **Gemini TTS with the `Zubenelgenubi` ("Casual") voice is now the default narration**, chosen by
  ear against Kore, Schedar, Algenib and Charon. `VOICE_ENGINE` defaults to `gemini` and
  `GEMINI_TTS_VOICE` to `Zubenelgenubi`, in code and in both workflows. The old default `Kore` is
  documented as "Firm", which is not the same as dry. Still $0 — the default model is free on input
  and output — and Chirp 3 HD remains the first fallback, which matters because every Gemini TTS
  model is preview; a test pins that fallback.
- **The style prompt follows Google's documented structure** (audio profile → director's notes on
  pace and inflection → paralinguistic detail) instead of naming an emotion, which their guidance
  says underperforms. It is now mostly restraint: the failure mode is a narrator who announces the
  joke.
- `test_gemini_absent_from_chain_by_default` retargeted to
  `test_gemini_absent_from_chain_when_another_engine_is_primary` — it encoded the pre-A/B "default
  is google" stance, but the invariant worth keeping is that selecting a different primary excludes
  Gemini entirely rather than leaving it a silent fallback.

### Added
- **`tools/tune_voice.py`** renders one script across the voices whose documented characteristics
  suit deadpan. Budget-aware (rule 13): paces calls for the 3 RPM ceiling, refuses to exceed 5 calls
  against the 10 RPD free tier, reports usage, and retries a transient 500 once so a blip does not
  cost a voice slot.

- **Per-engine delivery tags** (`voice._filter_tags`): the scriptwriter emits two tag families and
  each engine keeps only what it understands — `[pause]`/`[pause long]` become Chirp 3 HD `markup`,
  `[sarcastic]`/`[deadpan]`/`[dry]` pass through to Gemini TTS, and both are stripped for edge-tts
  and Kokoro. Allow-listed, with counts capped in code (`MAX_PAUSE_TAGS`/`MAX_STYLE_TAGS`, default
  3) rather than trusted to the prompt.
- **`gemini` TTS engine** — promptable narration via the Gemini Developer API, using the existing
  `GEMINI_API_KEY` and the already-pinned `google-genai`: no new dependency, no new credential.
  Default `gemini-2.5-flash-preview-tts` is free on input and output; `gemini-2.5-pro-preview-tts`
  has no free tier (~$1.27/month at 3 Shorts/day). Opt-in via `VOICE_ENGINE=gemini` and absent from
  the fallback chain otherwise. `VOICE_STYLE_PROMPT` sets the style; optional `GEMINI_TTS_API_KEY`
  isolates TTS from the grounded-ideation quota (rule 13).
- **`GOOGLE_TTS_SPEAKING_RATE`** (clamped 0.25–2.0) on the Chirp path.
- **`tools/compare_voices.py`** renders one script through Chirp, Gemini Flash and Gemini Pro so
  the model choice is made by ear.

### Fixed
- **Delivery tags were a no-op.** `synthesize()` stripped every tag before dispatching, so none
  could reach an engine — and emotion tags are not a Chirp feature regardless. Inline audio tags
  are a Gemini Developer API feature; Chirp reads pause tags only via `markup`.
- **The length guard miscounted tags as speech.** `[pause long]` contains a space, so whitespace
  splitting produced `[pause` and `long]` and counted both as spoken words at all three cap sites,
  silently shrinking the 25–30s budget. `_visible_words` now matches tags against the whole string,
  and truncation carries tags through while still cutting on a sentence boundary.
- **Gemini TTS returns raw 24 kHz PCM, not a WAV container** — it is wrapped before use; unwrapped,
  ffprobe and whisper cannot read the file.
- A Chirp **markup rejection now retries once as plain text** before failing over, so an unexpected
  syntax error costs the comic timing rather than the voice.
- The `voice` module docstring still described Kokoro as the primary engine long after Chirp took
  over.

### Changed
- **280 tests pass, 3 skipped** (was 242, 2).

## [Unreleased] — Content-engine audit: provider fixes, SFX retune, opt-in stat cards

### Fixed
- **GitHub Models provider was non-functional.** Wrong host (the retired Azure preview
  `models.inference.ai.azure.com`) and a bare model name where the API requires a publisher
  prefix. Now `https://models.github.ai/inference/chat/completions` with `openai/gpt-4o-mini`
  (a bare name is auto-prefixed). Requires a token scoped `models: read`.
- **Env-var names could never have existed as Actions secrets/vars** — GitHub rejects names
  beginning with `GITHUB_`. Renamed to `GH_MODELS_KEY`, `ENABLE_GH_MODELS`, `PREFER_GH_MODELS`,
  `GH_MODEL`.
- **`GH_PAT` removed from the LLM credential chain** (rule 5): it is the Telegram bot's Actions
  read+write PAT, and this repo's Actions hold the upload/DB/Telegram secrets.
- **`pillow` pinned** in `requirements.txt` — `graphics.py` imported it but it was undeclared,
  so CI would have failed on import while passing locally (rule 10).
- **Raw newlines in the scriptwriter's JSON example** made the target format invalid JSON and
  taught the model to emit the same; now shown escaped, with an explicit instruction.
- **SFX would have clipped the narration and sounded cheap.** A limiter now caps the summed mix
  (`amix normalize=0` has no headroom): verified 0.95 + 0.30 → +0.0003 dB clipped without it,
  −0.445 dB with it. Levels cut 0.5–0.6 → **0.18**, density every cut → **every 2nd cut**, and a
  **1.5s lead-in** keeps the hook clean.
- **SFX assets were not reproducible**: a shared module-level `Random` made generated waveforms
  depend on call order. Each generator now seeds its own (rule 10).

### Added
- **Opt-in PIL stat cards** (`ENABLE_GRAPHIC_CARDS`, default off): `graphics.py` — previously
  imported by nothing — is now wired into `subtitles.py`, sharing `_card_events` with the ASS path
  so the two treatments never double-draw. Overlaid via `-loop 1` + `enable='between(t,…)'` +
  `-shortest`, with a full-featured fallback to ASS text cards on any failure (rules 11, 14).
- **GitHub Models as an explicit opt-in third provider**: `ENABLE_GH_MODELS` adds it as a middle
  fallback, `PREFER_GH_MODELS` puts it first. Deliberately not enabled by mere token presence —
  a dead provider in the chain delays the Groq failover it exists to provide (rules 11, 13).
- **Knobs wired into `.env.example` and both workflows**: `ENABLE_SFX`, `SFX_VOLUME`,
  `SFX_EVERY_N_CUTS`, `SFX_DIR`, `ENABLE_GRAPHIC_CARDS`, `ENABLE_CHANNEL_TAGS`, `CAPTION_FONT_FILE`
  and the four `GH_*` keys — `ENABLE_SFX` defaults on, so it previously had no kill switch.

### Changed
- `audio_sfx.mix_sfx_events` writes PCM in bulk via `array` (0.42s → 0.19s per 28s track,
  byte-identical), caches each effect's decode, and skips malformed events instead of raising.
- Dropped dead code: `_SFX_NAMES`, the unused `extra_events` parameter, and a mid-file
  `import requests` in `llm.py`.
- **242 tests pass, 2 skipped** (was 215).

## [Unreleased] — Ideation diversity & virality

### Added
- **Two-stage news-anchored ideation** (`ideation_fallback.py`): a cheap **Stage 1** (Groq,
  `prefer_groq` to spare Gemini RPD) clusters the real news headlines into N **distinct**,
  share-worthy stories; **Stage 2** (Gemini grounded → ungrounded fallback) expands them into ideas.
  This breaks the single-call "mode collapse" that made batches similar, and makes freshness survive
  a grounding outage (Stage 2 still expands real current headlines).
- **`share_score` virality bar**: each idea carries a 0–1 "would someone send this to a friend?"
  score (defaults to `est_score` when omitted). On-demand ranking (`generate_ideas`/`seed_ideas`) is
  now **share_score-first, est_score-second**. Ranking-only — stripped before DB insert (no schema
  change) via `_to_rows`.
- **Token-overlap dedup backstop** (`_validate_and_clean`): drops same-story near-duplicates
  (Jaccard ≥ 0.6) that exact-title dedup missed.
- **Score calibration**: Stage 2 is instructed to rank ideas against each other and spread
  `share_score`/`est_score` across the full 0–1 range (no clustering at 1.0), so the share-first
  ranking produces a meaningful best-to-worst order. Verified live (0.95 → 0.55 spread).

### Changed
- **Trends demoted to a supplementary signal** (`trends.py`): a best-effort noise filter drops
  generic search junk (weather, calendars/festival-date lookups, `X vs Y` sports matchups,
  scorecards, lotteries). The ideation prompt now treats trends as optional flavour and **anchors on
  the real news feed**.
- **Ideation prompts rewritten** (both stages): one-idea-per-distinct-story, spread across categories,
  an explicit share test + curiosity-gap guidance — with every rule-6 hard guard intact (no
  fabrication, neutral framing, ≥2 real sources).
- Tests: +13 (`tests/test_ideation_fallback.py`, `tests/test_trends.py`); suite **204 pass** (gated
  live tests deselected).

## [0.4.3] — 2026-06-17 — Retention refinements v2

### Added
- **Brand-logo bug** (`assembly.py`): the circular *But It Matters* logo (committed at
  `assets/brand/logo.png`) is overlaid small + semi-transparent in the top-right of every reel.
  Fail-soft (skips if the file is absent) and polish-gated. Knobs: `ENABLE_BRAND_BUG`, `BRAND_LOGO`,
  `BRAND_LOGO_HEIGHT`/`_OPACITY`/`_MARGIN`.
- **Source-citation lower-third** (`subtitles.py` + `production.py`): a brief "Source: domain" line
  (derived from the idea's first source URL) shown for the first ~3s — credibility + news-compliance
  (rule 6). Knobs: `ENABLE_SOURCE_CITE`, `SOURCE_CITE_SECONDS`.
- **Loop-friendly endings** (`assembly.py`): the final clip reuses the opening shot so replays don't
  jar. Knob: `ENABLE_SEAMLESS_LOOP`.

### Changed
- **25-30s length now enforced** (`scriptwriter.py`): the hook punch-up pass carried stale long-form
  instructions (~110-130 words) and a loose 80-220 word guard, ballooning reels to ~38s. The prompt
  now forbids lengthening, the guard accepts only ≤ `SCRIPT_MAX_WORDS` (default 80), and a final hard
  backstop truncates an over-long body to its last full sentence.
- **Music ducking** (`assembly.py`): the flat 10% music bed is replaced by sidechain ducking — the
  music dips under the narration and swells between sentences (clearer speech). Polish-gated; the
  fail-soft retry uses the old flat mix. Knob: `ENABLE_DUCKING`.

## [0.4.2] — 2026-06-17 — Premium edit polish (transitions + cinematic grade)

### Added
- **Crossfade transitions** (`assembly.py`): hard `concat` between cuts replaced by a chained
  `xfade` (default 0.35s overlap, `ENABLE_XFADE` / `XFADE_SECONDS`). `_ordered_clips` is now
  overlap-aware so crossfaded reels still over-cover the narration; `overlap=0` reproduces the
  old hard-cut slice count exactly.
- **Cinematic color grade** (`assembly.py`): a single grade pass over the final stream
  (`eq` contrast/saturation + warm `colorbalance`) that unifies independently-generated AI shots
  into one house look — the biggest premium lever. Plus **vignette** and subtle **film grain**.
  All independently toggle-gated (`ENABLE_GRADE`/`GRADE_CONTRAST`/`GRADE_SATURATION`,
  `ENABLE_VIGNETTE`, `ENABLE_GRAIN`/`GRAIN_STRENGTH`).
- **Ken Burns motion variety** (`visuals.py`): image clips now alternate slow zoom-in / zoom-out
  by index instead of always zooming in, for less monotonous motion. Deterministic per index.

### Changed
- **Fail-soft render** (`assembly.py`): `assemble()` builds the polished filtergraph first and, on
  any ffmpeg error, automatically retries with the plain graph — a polish failure can never lose
  the reel or kill the daily batch (rules 11, 14). `_build_cmd` gains a `polish` flag.

## [0.4.1] — 2026-06-15 — Short-form 12-20s bites + cloud voice/news hotfix

### Changed
- **Format → 12-20 second Shorts** (`scriptwriter.py`, `ideation_fallback.py`): scripts are now a
  tight ~30-45 word bite (HOOK → THE NEWS → one honest "why it matters" clause → 2-3 word CTA),
  down from ~110-130 words. Ideation proposes trending, single-development stories sized for
  12-20s. One why-it-matters clause is kept so it stays original (monetization gate), not a bare
  summary. `key_points` → 2-3; word guard → ~30-45. The reel auto-follows the narration length.

### Fixed
- **Google TTS error visibility** (`voice.py`): `_synthesize_google` strips/encodes the key and
  raises with Google's actual response body on non-200 (cloud logs previously showed only an
  opaque "400 Client Error", hiding the real cause).
- **News empty-URL** (`news.py`): an empty `NEWS_RSS_URL` repo var (`""` in CI) now falls back to
  the default feed instead of becoming an invalid request URL.

## [0.4.0] — 2026-06-15 — Content-quality overhaul Phase B: story-specific visuals + curated topics

Phase B of the overhaul (same spec as 0.3.0). Layers story-specific on-screen text over the B-roll,
seeds ideation with real news, and wires Google Chirp 3 HD live (operator added the key).

### Added
- **On-screen key-point text cards** (`scriptwriter.py`, `subtitles.py`, `production.py`): the
  scriptwriter emits 3-5 ultra-short `key_points`; subtitles burns them as sparse bold mid-frame
  cards (new `Card` ASS style) distributed across the reel. Layers story-specific TEXT over the
  generic stock B-roll — the core fix for the "AI-slop" look. Knobs `ENABLE_TEXT_CARDS`, `CARD_SECONDS`.
- **Curated news topics** (`src/news.py`): ideation is now seeded by real Google News RSS headlines
  (India locale, no key) alongside trends, so ideas track actual current stories. Best-effort
  (rule 11); override via `NEWS_RSS_URL`.

### Changed
- **`tools/list_google_voices.py`** now loads `.env` (dev convenience).
- **Live voice wired**: `en-IN-Chirp3-HD-Kore` selected + verified end-to-end; GitHub secret
  `GOOGLE_TTS_API_KEY` + variable `GOOGLE_TTS_VOICE` set so cloud runs narrate in Chirp 3 HD.
- **171 tests pass** (was 161; +10). New knobs wired into both workflows + `.env.example`.

## [0.3.0] — 2026-06-15 — Content-quality overhaul: honest framing, near-human voice, karaoke captions

Phase A of the content-quality overhaul (spec: `docs/superpowers/specs/2026-06-15-content-quality-overhaul-design.md`).
**Reverses the earlier "max hype" tuning** — 2026's algorithm suppresses click→swipe title/content
mismatch, and YouTube's Inauthentic-Content policy penalises low-effort automation. Budget raised
**$0 → ≤ $5/month** (Google Cloud TTS; free at our volume).

### Added
- **Google Cloud TTS Chirp 3 HD voice** (`voice.py`): near-human `en-IN` narration via the v1 REST
  endpoint + API key. New ordered fallback **chain** `google → edge-tts (en-IN Neerja) → Kokoro`,
  resolved at call time so a missing key just advances. Helper `tools/list_google_voices.py` lists
  en-IN Chirp3-HD voices. Knobs `VOICE_ENGINE`, `GOOGLE_TTS_API_KEY/VOICE/LANGUAGE`.
- **Active-word karaoke captions** (`subtitles.py`): each word fills to a highlight colour as it's
  spoken (ASS `\kf`), in a bundled OFL **Montserrat** font (`assets/fonts/`, staged so libass
  resolves it via a relative `fontsdir`). Knobs `CAPTION_FONT`, `CAPTION_HIGHLIGHT_COLOR`.
- **`ENABLE_HUMAN_ANGLE`**: the script must carry a genuine "why it matters" take — the originality /
  anti-"AI-slop" signal under YouTube's 2026 policy.

### Changed
- **De-hyped script + ideation prompts** (`scriptwriter.py`, `ideation_fallback.py`): honest curiosity
  with promise↔payoff alignment over clickbait/"max hype"; titles must stay true to the video. Hook
  punch-up now rewrites only genuinely flat hooks (`HOOK_MIN_SCORE` 8 → 7). Accuracy hard-line intact.
- **Default voice** is Google Chirp 3 HD (was Kokoro int8 `af_heart`, an American voice).
- **Default `CAPTION_WORDS`** 2 → 3 (readable karaoke phrases).
- **Cost target** $0 → ≤ $5/month (CLAUDE.md rule 2, README, docs/01, docs/04, docs/07 synced).
- **161 tests pass** (was 153; +8).

## [Unreleased] — Virality tuning from first real analytics

First real-traffic learning: one Short ("Oil Export Wars", 1,032 views) hugely outperformed dry
explainers. Retuned the generators toward conflict/curiosity framing (operator chose max hype) and
closed the learning loop so winning *titles* — not just topics — feed back into ideation.

### Added
- **`scripts.title`** column + persistence: the punchy PUBLISHED title is now stored, so
  `db.top_performing_titles()` learns which title STYLE wins (returns `"title" — N views`), not the
  dry idea topic.
- **`llm.generate(prefer_groq=True)`**: tries Groq first to reserve Gemini's scarce free RPD
  (rule 13) for grounded web research. The no-web tasks — hook punch-up + B-roll keyword extraction
  — now route to Groq; grounded research stays on Gemini. Failover chain intact.
- **Telegram control bot** (`telegram-bot/`, Vercel webhook, stdlib-only): instant commands —
  `/makeshort [n]` (starts the GitHub Action), `/today`, `/stats`, `/pending`, `/latest`, `/help`.
  Operator-only (chat-id + secret-token gated). Helper `tools/set_telegram_webhook.py` + setup guide.
- **Brand description footer**: every Short's description gets a branding + subscribe-CTA + 3 brand
  hashtags footer (`production._with_footer`), idempotent + length-capped, complementing (not
  duplicating) the caption/sources/disclosure. Toggle `ENABLE_DESC_FOOTER`; override `DESCRIPTION_FOOTER`.

### Changed
- **Scriptwriter** (`template-N`): viral title formulas (power-words, curiosity gap, conflict,
  ALL-CAPS, "watch till the end"); first caption line is now a curiosity hook; spoken hook opens a
  loop paid off at the end. Hype the framing — accuracy stays the one hard line (no fabricated facts).
- **Ideation**: selects topics by **scroll appeal** (conflict/drama/sports/global stakes) over dry
  local policy; seeds punchy hook titles instead of "X explained"; ingests winning title styles.
- **Frame-1 hook banner** (`subtitles.py`): the punchy title is burned as a bold yellow top-of-frame
  banner for the first `HOOK_SECONDS` (1.8s) — that frame is the in-feed thumbnail, the biggest free
  CTR lever. Emoji-stripped/uppercased/wrapped; toggle `ENABLE_HOOK_CAPTION`.
- **Faster, staggered B-roll cuts** (`assembly.py`): cut length is now `CLIP_SECONDS` (default 3.5s,
  was fixed 6s) for Shorts-style pattern-interrupts; repeated clips advance their start offset so a
  repeat shows a *different* segment, not the same opening twice.
- **Seamless loop ending** (`template-N`): the closing CTA now loops back into the hook so an
  auto-replay flows from the last line into the first (replay = more watch-time = more reach).
- **Scroll-stop hook judge** (`scriptwriter._punch_up_hook`): a cheap free-API pass scores the
  opening hook 1-10 and, only if weak (< `HOOK_MIN_SCORE`, default 8), rewrites the title + opening
  for more punch — forbidden from adding/altering any fact, fail-soft (keeps the original on any
  error/bad rewrite). Toggle `ENABLE_HOOK_JUDGE`.
- **Dramatic voice pacing** (`voice.py`, Kokoro): narration is synthesized sentence-by-sentence and
  rejoined with controlled silence — tighter `PAUSE_BETWEEN` (0.18s) mid-script, a longer
  `PAUSE_BEFORE_PAYOFF` (0.5s) beat before the final line. Redistributes pauses (snappier + one
  dramatic beat), doesn't lengthen the reel. Toggle `ENABLE_DRAMATIC_PACING`; edge-tts stays one-shot.

### Knobs (repo Variables)
- `ENABLE_HOOK_CAPTION`, `HOOK_SECONDS`, `CLIP_SECONDS`, `ENABLE_HOOK_JUDGE`,
  `ENABLE_DRAMATIC_PACING`, `PAUSE_BETWEEN`, `PAUSE_BEFORE_PAYOFF` added to both workflows.

## [0.2.0] — 2026-06-10 — Public channel + quality/discoverability/learning

Post-MVP enhancements; channel went **public** and the pipeline got materially better.

### Added
- **Trending ideation** (`trends.py`): live Google-Trends-India seeds + topic filter that allows
  neutral politics/government/court coverage (operator choice) with hard guards.
- **Web-grounded ideation**: Gemini Google Search grounding → real, current, sourced ideas;
  falls back to ungrounded JSON mode.
- **Kokoro humanized TTS** (primary) with edge-tts fallback.
- **AI / photo visuals**: `VISUAL_SOURCE` = `ai` (Cloudflare Flux) / `photos` (Pexels + Ken Burns)
  / `video`; image sources fall back to stock video.
- **Background music** bed (`assets/music/`, FFmpeg mix under narration).
- **SEO**: scriptwriter-generated optimized titles + 10–15 tags; tag budget cap.
- **Analytics** (`analytics.py`): pull view/like/comment stats → rank winners → feed back into
  ideation. `analytics.yml` wired.
- **Tuning knobs** as repo variables: `IMAGE_STYLE`, `CAPTION_WORDS`, `KOKORO_SPEED/VOICE`,
  `MUSIC_VOLUME`, `VISUAL_SOURCE`, `YOUTUBE_PRIVACY`.

### Changed
- Script tone → natural, thrilling, scroll-stopping (shorter ~110–130 words).
- B-roll keywords translate proper nouns → filmable stand-ins (courtroom, parliament, rocket).
- Captions group ~2 words + clean stray punctuation; minimal AI-disclosure line.
- CI caches Kokoro/whisper models + pip; `requirements.txt` pinned.

### Fixed
- **Anti-hallucination guardrails** (ideation + scriptwriter) after a fabricated "Claude Fable 5"
  reel — only real, source-supported facts.
- **Duplicate-publish gap**: idea-level idempotency before scripting.
- LLM-JSON robustness (`strict=False`, grounded→ungrounded fallback); disabled gemini-2.5-flash
  thinking so JSON replies aren't truncated. Robust boolean config parsing.

## [0.1.0] — 2026-06-09 — Phase-1 MVP live 🎉

First Shorts published fully in the cloud (machine-off): idea → Telegram approval → script →
voice → visuals → assemble → subtitles → YouTube. The pipeline (10 modules + orchestrator) is
built, tested (101 pass), deployed (GitHub Actions secrets, on-demand `make-short` workflow),
and proven in production.

### Fixed (real LLM-output failures surfaced by cloud runs)
- Parse LLM JSON with `strict=False` (raw control chars in grounded responses).
- Grounded ideation falls back to ungrounded JSON-mode on malformed/truncated grounded JSON.
- Disabled `gemini-2.5-flash` thinking (`thinking_budget=0`) so JSON replies aren't truncated;
  raised scriptwriter token budget.

### Added
- Foundation: imported the 8-doc design package into [docs/](docs/).
- [CLAUDE.md](CLAUDE.md) — 18 operating rules for agents working in this repo.
- [STATUS.md](STATUS.md) — living progress log.
- [README.md](README.md) and this changelog.
- Phase-1 scaffolding: `src/` module stubs with typed contracts, functional `config.py`
  (+ passing `tests/test_config.py`), `routines/ideation.md`, `templates/` (N/D/A/C),
  `.github/workflows/` skeletons, `requirements.txt`, `.env.example`, `.gitattributes`.
- `tools/get_youtube_token.py` — one-time OAuth helper to generate the YouTube refresh token.
- `tools/verify_youtube.py` — checks the YouTube refresh token mints a live access token.
- **Module: `db.py`** — Supabase data layer (typed helpers + `find_post` idempotency check),
  with a live integration test (`tests/test_db_integration.py`). Supabase project provisioned:
  5 tables + RLS + secret-key access.
- **Module: `llm.py`** — shared free-tier text engine with Gemini→Groq failover (rule 11),
  JSON mode, and env-overridable models. Unit tests (`tests/test_llm.py`, 5 cases) mock both
  providers to verify the failover chain with no keys/network.
- **Module: `scriptwriter.py`** — turns an approved idea into `{script_id, script_body,
  caption, hashtags[]}` via Template N + `llm.py`, persisting to `scripts`. Enforces the
  monetization gate in code (source links, AI-disclosure line, `#Shorts`). Unit tests
  (`tests/test_scriptwriter.py`, 8 cases) mock `llm`/`db` — no keys/network/DB.
- **Module: `voice.py`** — edge-tts narration (`en-IN`, env-overridable), returns
  `(audio_path, duration_s)` measured from boundary events; deterministic filename for
  idempotent reruns; wrapped for a Phase-2 Kokoro fallback. Tests (`tests/test_voice.py`,
  6 cases) mock the stream + one live synthesis that skips offline.
- **Module: `visuals.py`** — `extract_keywords` (LLM + heuristic fallback) and `fetch_broll`
  (Pexels CC0 portrait B-roll → Pixabay backup), with variety interleaving, target-duration
  coverage, and content-hashed idempotent caching. Tests (`tests/test_visuals.py`, 11 cases)
  mock HTTP + one live Pexels search/download.
- **Module: `assembly.py`** — composes B-roll + narration into a 1080×1920 H.264 reel via the
  FFmpeg binary (scale-to-fill/center-crop, ~6s cuts, concat, trim to narration length, mux
  audio, `+faststart`). Robust binary resolution (env → PATH → winget). Tests
  (`tests/test_assembly.py`, 7 cases) cover argv build + a **live end-to-end render**.
- **Module: `subtitles.py`** — faster-whisper word-level timestamps → karaoke `.ass`
  (one word at a time, gap-filled) → FFmpeg burn-in (large bold lower-third, pixel-baked).
  Tests (`tests/test_subtitles.py`, 9 cases) mock whisper+ffmpeg + a **live** transcribe+burn.
- **Module: `publish_youtube.py`** — resumable `videos.insert`, sets the official AI-disclosure
  flag (`status.containsSyntheticMedia`) + `#Shorts`, records the post, deletes the local file,
  and is idempotent against cron retries. Tests (`tests/test_publish_youtube.py`, 8 cases) are
  fully mocked, with a gated live PRIVATE upload behind `YOUTUBE_LIVE_UPLOAD_TEST=1`.
- **Module: `ideation_fallback.py`** — free-API (Gemini→Groq) ideation mirroring the Routine's
  JSON contract, with source/field validation, dedup, score clamping, idempotency, and a
  thin-digest guard. Tests (`tests/test_ideation_fallback.py`, 9 cases) mock llm/db + one live run.
- **Module: `approval.py`** — Telegram Morning Digest over the Bot HTTP API (requests): per-idea
  messages with Approve/Reject buttons, long-poll callback handling, soft approval cap, and a
  chat-id security check. Tests (`tests/test_approval.py`, 11 cases) mock the API + one gated live send.
- **Orchestrator: `production.py`** — wires the full daily cycle (bootstrap ideas+digest →
  drain approvals → produce approved queue), idempotent and fail-soft per reel with a Telegram
  failure alert and a daily cap. Tests (`tests/test_production.py`, 8 cases) mock every module.
  **Phase-1 pipeline is code-complete; only go-live steps remain.**
- **Telegram digest: third "⏭️ Pass" button** → new `passed` idea status (a soft skip, distinct
  from a hard reject; not posted). Wired through `db.IDEA_STATUSES` + `approval`.
- **On-demand "Make a Short":** `make-short.yml` (`workflow_dispatch`) + `production.make_on_demand`
  + `ideation_fallback.generate_ideas(n)` — click *Run workflow* → propose ideas to Telegram →
  tap Make-it → produce + reply with the link. Machine-off, frequency under operator control.
- **Web-researched ideas in-cloud:** `llm.generate_grounded()` (Gemini + Google Search grounding)
  gives ideation live web research with real source URLs, inside the GitHub Action — no PC, no
  routine. `ideation_fallback` researches first, falls back to ungrounded Gemini→Groq. (The
  cloud Anthropic Routine was retired: read-only git token + custom connectors can't attach.)

### Changed
- Rebranded **Newsence → But It Matters** (handle `@butitmatters`) across all files;
  `CHANNEL_NAME` default updated.
- **`requirements.txt`:** `google-generativeai` → **`google-genai`** (the former was
  deprecated/EOL in late 2025; `llm.py` uses the current `from google import genai` SDK).
- **`requirements.txt`:** dropped `ffmpeg-python` — `assembly.py` calls the FFmpeg binary
  directly via subprocess (FFmpeg is a documented system dependency).
- **`requirements.txt`:** dropped `python-telegram-bot` — `approval.py` uses the Telegram Bot
  HTTP API directly via `requests` (simpler for a polling script).
