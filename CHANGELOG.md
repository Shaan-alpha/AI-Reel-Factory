# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); this project uses
[Semantic Versioning](https://semver.org/). Phase milestones are tagged
(`v0.1.0` = Phase-1 MVP done).

## [Unreleased]

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

### Changed
- Rebranded **Newsence → But It Matters** (handle `@butitmatters`) across all files;
  `CHANNEL_NAME` default updated.
- **`requirements.txt`:** `google-generativeai` → **`google-genai`** (the former was
  deprecated/EOL in late 2025; `llm.py` uses the current `from google import genai` SDK).
- **`requirements.txt`:** dropped `ffmpeg-python` — `assembly.py` calls the FFmpeg binary
  directly via subprocess (FFmpeg is a documented system dependency).
- **`requirements.txt`:** dropped `python-telegram-bot` — `approval.py` uses the Telegram Bot
  HTTP API directly via `requests` (simpler for a polling script).
