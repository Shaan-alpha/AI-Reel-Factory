# STATUS — AI Reel Factory ("But It Matters")

> **Living progress log.** Every agent updates this before finishing a task
> (rule #1 in [CLAUDE.md](CLAUDE.md)). Keep it short, current, and honest.
> Newest entry at the top of the log.

**Phase:** 1 — MVP (4–5 captioned YouTube Shorts/day)
**Version:** 0.0.9 (pre-MVP — first full reel renders end-to-end; 43/43 tests pass)
**Last updated:** 2026-06-09
**Brand:** But It Matters · YouTube handle **@butitmatters** · Telegram bot **@ai_reel_factory_bot**

---

## Snapshot

| Area | State |
|------|-------|
| Design / docs | ✅ Complete — 8 docs in [docs/](docs/) |
| Project rules | ✅ Written — [CLAUDE.md](CLAUDE.md) |
| Repo scaffolding (src/, routines/, templates/, tests/, workflows) | ✅ Done — stubs + contracts |
| `config.py` | ✅ Functional + tested (4/4 pass) |
| Script templates (N, D, A, C) | ✅ Written |
| Routine prompt (`routines/ideation.md`) | ✅ First draft |
| Accounts & API keys | ✅ **ALL collected + verified** — Gemini · Groq · Supabase(secret) · Telegram · Pexels · Claude token · YouTube |
| Supabase database | ✅ 5 tables + RLS + secret-key writes confirmed |
| YouTube OAuth | ✅ Verified (upload+readonly); token bound to the correct **@butitmatters** channel |
| YouTube handle `@butitmatters` | ✅ Secured (IG/TikTok not checked — Phase 3) |
| YouTube channel *title* | ✅ Renamed to **But It Matters** (matches handle + CHANNEL_NAME) |
| Pipeline logic (modules) | 🟡 `db.py` + `llm.py` done + tested; other modules still stubs |
| Local `.venv` | ✅ pytest + supabase + google-genai + groq + edge-tts (suite green) |
| FFmpeg (system dep) | ✅ Installed locally — winget `Gyan.FFmpeg` 8.1.1 (assembly module) |

## Module progress (Phase 1)

| # | Module | Status |
|---|--------|--------|
| 1 | Ideation (Claude Routine + fallback) | 🟡 Routine prompt drafted; `ideation_fallback.py` stub (llm.py ready) |
| 2 | Approval (Telegram) | 🟡 Stub + contract |
| 3 | Scriptwriter (Gemini/Groq) | ✅ Done — Template N via `llm.py`; compliance enforced; 8 unit tests |
| 4 | Voice (edge-tts) | ✅ Done — en-IN voice, duration measured; 6 tests (incl. live synth) |
| 5 | Visuals (Pexels/Pixabay) | ✅ Done — LLM keywords + CC0 portrait B-roll; 11 tests (incl. live) |
| 6 | Assembly (FFmpeg) | ✅ Done — 1080×1920 H.264 reel; 7 tests (incl. live full render) |
| 7 | Subtitles (faster-whisper) | 🟡 Stub + contract |
| 9 | Publish (YouTube) | 🟡 Stub + contract |
| — | `config.py` / `db.py` / `llm.py` | config ✅ · **db ✅** · **llm ✅ (Gemini→Groq failover, 5 unit tests)** |

Legend: ✅ done · 🟡 scaffolded (stub/contract) · ⬜ not started

## Next actions

- ✅ **All credentials collected + verified** (Supabase secret key + YouTube OAuth done).
1. **Build the pipeline module-by-module** (rule 7): `db.py` ✅ → `llm.py` ✅ →
   `scriptwriter.py` ✅ → `voice.py` ✅ → `visuals.py` ✅ → `assembly.py` ✅ →
   **`subtitles.py`** (next — faster-whisper karaoke captions, ★ in MVP) →
   `publish_youtube.py`; plus `ideation_fallback.py` + `approval.py` (front end);
   → wire `production.py`.
   **NOTE:** FFmpeg 8.1.1 installed locally (winget `Gyan.FFmpeg`); CI must install it onto PATH.
2. **GitHub Actions secrets:** mirror every `.env` value into the repo's Actions secrets
   (`gh secret set …`) before the first cron run.
3. Decide ideation runner: **Anthropic Routines** (recommended) vs Oracle VM cron; create the
   Routine from `routines/ideation.md`.
4. (Phase 3) Check `@butitmatters` on Instagram + TikTok before cross-posting.

## Open decisions

- **Ideation runner:** Anthropic Routines vs Oracle VM cron (lean Routines).

## Blockers

- _None._

---

## Log

### 2026-06-09 — Module: assembly.py — FIRST FULL REEL RENDERS END-TO-END
- Implemented [src/assembly.py](src/assembly.py): `assemble(audio_path, clip_paths, out_path)`
  calls the **FFmpeg binary** directly (subprocess) — normalizes each clip (scale-to-fill +
  center-crop to 1080×1920, ~6s slice), concats, trims to the narration length (via `ffprobe`),
  and muxes the narration → H.264/yuv420p/AAC `.mp4`, `+faststart`. Clips are cycled to
  over-cover the audio; cuts land ~every 6s (retention + copyright, docs/08 §3).
- Binary resolution: `FFMPEG_BINARY`/`FFPROBE_BINARY` env → PATH → Windows winget fallback;
  fails loud if absent (rule 14). **Installed FFmpeg 8.1.1** locally (`winget install Gyan.FFmpeg`).
- **MVP scope** (rule 16): no Ken Burns / music bed yet — deferred until the core is proven;
  easy follow-ups. `requirements.txt`: dropped `ffmpeg-python` (binary called directly).
- Added [tests/test_assembly.py](tests/test_assembly.py): 6 unit cases (argv build, clip cycling,
  input validation) + 1 **live end-to-end** test — edge-tts → Pexels → FFmpeg renders a real
  1080×1920 reel with audio, length within 1.5s of narration. **Suite: 43 passed.**
- ⭐ The text→audio→visuals→video chain is now complete: an approved idea produces a real,
  watchable (un-captioned) Short. Next: burn in karaoke captions (`subtitles.py`).

### 2026-06-09 — Module: visuals.py implemented + tested (live)
- Implemented [src/visuals.py](src/visuals.py): `extract_keywords(script_body, n)` (LLM with a
  frequency-heuristic fallback, rule 11) + `fetch_broll(keywords, target_seconds, out_dir)` →
  CC0 vertical clips from **Pexels** (→ **Pixabay** backup). Picks portrait mp4 closest to
  1080w, interleaves across keywords for variety, downloads until ~target coverage (8s/clip,
  matching assembly cuts), content-hashed filenames for idempotent caching (rule 12).
- **Verified the Pexels video endpoint** is `https://api.pexels.com/videos/search` (no `/v1`),
  auth via bare `Authorization` header; live search returns true 1080×1920 portrait clips.
- Added [tests/test_visuals.py](tests/test_visuals.py) — 10 mocked cases (keywords LLM+heuristic,
  portrait selection, coverage/stop, idempotent cache, Pixabay fallback, error paths) + 1 **live**
  Pexels search+download (skips offline). **Suite: 36 passed.**

### 2026-06-09 — Module: voice.py implemented + tested (live)
- Implemented [src/voice.py](src/voice.py): `synthesize(script_body, out_dir) → (audio_path,
  duration_s)` via **edge-tts** (free, no key). Uses `stream_sync()` to write the MP3 and
  measure duration from boundary events in one pass — no extra audio-probe dep. Deterministic
  filename `narration_<sha1>.mp3` (idempotent reruns, rule 12). Voice/rate env-overridable
  (`VOICE`=`en-IN-NeerjaNeural`, `VOICE_RATE`). edge-tts wrapped so Kokoro slots in (Phase 2).
- **edge-tts 7.2.8 gotcha:** default boundary is `SentenceBoundary`, not `WordBoundary` (the
  older docs). Duration now reads either type. Found via a real stream-type probe.
- Added [tests/test_voice.py](tests/test_voice.py) — 5 mocked cases (write, duration math,
  deterministic name, empty/no-audio/error wrapping) + 1 **live** edge-tts synth (skips
  offline). Confirmed a real ~4s en-IN MP3 renders. **Suite: 25 passed.**

### 2026-06-09 — Module: scriptwriter.py implemented + tested
- Implemented [src/scriptwriter.py](src/scriptwriter.py): `write_script(idea, template='N')`
  builds the Template-N prompt, calls `llm.generate(json=True)`, parses the JSON (tolerant of
  markdown fences), and persists via `db.insert_script`. Returns `{script_id, script_body,
  caption, hashtags}`.
- **Monetization-gate enforcement in code, not trusted to the LLM** (docs/08 §1-3): source
  links + the AI-disclosure line are guaranteed in the caption, and `#Shorts` in the hashtags —
  added only if missing (no duplication). Soft word-count warning (~130-150) per rule 14.
- Only Template N is wired (rule 9 / YAGNI); D/A/C raise a loud `ValueError`.
- Added [tests/test_scriptwriter.py](tests/test_scriptwriter.py) — 8 cases mocking `llm` + `db`
  (no keys/network/DB): happy path, compliance enforcement, no-duplication, fenced JSON,
  empty-body / unparseable / unsupported-template / missing-id errors. **Suite: 19 passed.**

### 2026-06-09 — Module: llm.py implemented + tested; SDK + venv fixes
- Implemented [src/llm.py](src/llm.py): `generate(prompt, *, json, max_tokens)` with a
  **Gemini → Groq** failover chain (rule 11) — logs + fails over on error/quota/empty, raises
  only when *every* provider fails. JSON mode for both; models overridable via `GEMINI_MODEL`/
  `GROQ_MODEL` env. Defaults: `gemini-2.5-flash`, `llama-3.3-70b-versatile`.
- Added [tests/test_llm.py](tests/test_llm.py) — 5 cases mocking both providers (no keys/network)
  to prove the failover, empty-response handling, all-fail RuntimeError, and json/max_tokens
  threading. **Suite: 11 passed** (4 config + 6 db live + 5 llm).
- **SDK fix:** `requirements.txt` `google-generativeai` → **`google-genai`** (the old SDK was
  deprecated/EOL late 2025; verified the current `from google import genai` API via Context7).
- **Env:** created local `.venv` (first one) and installed pytest + supabase + google-genai +
  groq so the suite collects and runs green from a clean checkout. (Lock file deferred until
  the heavier video deps install — `pip freeze` now would be a partial/misleading lock.)

### 2026-06-06 — YouTube channel binding confirmed
- First OAuth pass was bound to the wrong (main) channel + then revoked. Re-ran cleanly:
  added `youtube.readonly` scope, regenerated the token selecting the **@butitmatters**
  channel, no post-revoke. `tools/verify_youtube.py` reads the bound channel and confirms it.
- Bound channel title is `Why It Matters??`; user confirmed it's the project channel and set
  the canonical brand to **But It Matters** (matches the handle + repo). Cosmetic to-do:
  rename the YT channel title to "But It Matters".

### 2026-06-05 — All credentials complete (YouTube OAuth verified)
- Generated YouTube OAuth creds (Desktop-app client + published consent screen) and added
  `YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN` to `.env`.
- Added [tools/verify_youtube.py](tools/verify_youtube.py); confirmed the refresh token mints
  a live access token. **Every API key is now collected and verified** — the full pipeline
  (incl. `publish_youtube.py`) is unblocked.

### 2026-06-05 — Module: db.py implemented + tested
- Implemented [src/db.py](src/db.py) on supabase-py 2.31.0: `get_client()` (cached, secret
  key), `insert_ideas`, `get_pending_ideas`, `set_idea_status`, `get_approved_ideas`,
  `insert_script`, `insert_post`, `find_post` (idempotency helper, rule 12). Added a
  `produced` idea status so cron retries skip shipped reels.
- Added [tests/test_db_integration.py](tests/test_db_integration.py): full idea→post cycle
  against the live DB, auto-skips without creds. **Suite: 6 passed.**
- User swapped `SUPABASE_KEY` to the `sb_secret_…` key — RLS-protected writes confirmed working.

### 2026-06-05 — Supabase database provisioned
- Created all 5 tables (`ideas`, `scripts`, `posts`, `analytics`, `hook_performance`) on the
  `ai-reel-factory` project (Postgres 17, Seoul) via the Supabase MCP, matching the
  [docs/03](docs/03-setup-guide.md) §4 schema (FKs + identity PKs + array/timestamp defaults).
- **RLS enabled** on every table (no policies → public/anon key denied; the server-side
  `sb_secret_…` key bypasses RLS). Cleared an advisor WARN by revoking public EXECUTE on the
  pre-existing `rls_auto_enable()` event-trigger (auto-RLS behavior unaffected).
- Smoke-tested insert → read (defaults applied) → delete. Security advisor now clean
  (only expected INFO `rls_enabled_no_policy`).
- User completed `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` in `.env` (for the Routine).
- **Remaining:** swap `SUPABASE_KEY` to the `sb_secret_…` key (MCP only exposes publishable keys).

### 2026-06-05 — Branding + setup underway
- Channel handle `@newsence` was taken → rebranded to **But It Matters** (`@butitmatters`,
  secured on YouTube). Renamed across all repo files.
- Collected keys into `.env` (gitignored): Gemini, Groq, Supabase (publishable — swap to
  secret), Telegram bot `@ai_reel_factory_bot` (+ chat id, in `.env`), Pexels. Verified
  Gemini + Pexels return HTTP 200.
- Added [tools/get_youtube_token.py](tools/get_youtube_token.py) to generate the YouTube
  refresh token (one-time OAuth), with step-by-step setup notes.
- Repo home decision: use the **public** `Shaan-alpha/AI-Reel-Factory` repo (unlimited
  Actions minutes). Secret-scanned tracked files before pushing — clean.

### 2026-06-05 — Phase-1 scaffolding
- Created the repo skeleton from [docs/02-implementation-plan.md](docs/02-implementation-plan.md) §0:
  `src/` (10 module stubs + functional `config.py`), `routines/ideation.md` (first-draft
  Routine prompt), `templates/` (N, D, A, C), `tests/`, `.github/workflows/` (skeletons,
  manual-trigger), `requirements.txt`, `.env.example`, `.gitattributes`.
- Module stubs carry their typed input→output contract + `NotImplementedError` (no pipeline
  logic yet, per scope). Build them in order, in isolation (rule 7).
- `config.py` is real (fail-loud, rule 14) and covered by `tests/test_config.py` — **4/4 pass**.
- Workflows default to `workflow_dispatch`; cron stays commented out until modules work.

### 2026-06-05 — Foundation set up
- Imported the 8-doc design package into [docs/](docs/) from the `AI Idea` source folder.
- Wrote [CLAUDE.md](CLAUDE.md): 18 operating rules (docs-as-memory, free-first, no
  self-attribution, ToS boundary, news compliance, runtime reliability, versioning).
- Added this STATUS.md, [README.md](README.md), and [CHANGELOG.md](CHANGELOG.md).
- No pipeline code yet — foundation only by design.
