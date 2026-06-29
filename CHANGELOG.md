# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); this project uses
[Semantic Versioning](https://semver.org/). Phase milestones are tagged
(`v0.1.0` = Phase-1 MVP done).

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
