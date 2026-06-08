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

### Changed
- Rebranded **Newsence → But It Matters** (handle `@butitmatters`) across all files;
  `CHANNEL_NAME` default updated.
- **`requirements.txt`:** `google-generativeai` → **`google-genai`** (the former was
  deprecated/EOL in late 2025; `llm.py` uses the current `from google import genai` SDK).
