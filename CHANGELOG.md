# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); this project uses
[Semantic Versioning](https://semver.org/). Phase milestones are tagged
(`v0.1.0` = Phase-1 MVP done).

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
