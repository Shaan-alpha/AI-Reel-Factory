# STATUS — AI Reel Factory ("But It Matters")

> **Living progress log.** Every agent updates this before finishing a task
> (rule #1 in [CLAUDE.md](CLAUDE.md)). Keep it short, current, and honest.
> Newest entry at the top of the log.

**Phase:** 1 — MVP (4–5 captioned YouTube Shorts/day)
**Version:** 0.0.4 (pre-MVP — DB layer live + integration-tested)
**Last updated:** 2026-06-05
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
| Pipeline logic (modules) | 🟡 `db.py` done + tested; other modules still stubs |

## Module progress (Phase 1)

| # | Module | Status |
|---|--------|--------|
| 1 | Ideation (Claude Routine + fallback) | 🟡 Routine prompt drafted; `ideation_fallback.py` stub |
| 2 | Approval (Telegram) | 🟡 Stub + contract |
| 3 | Scriptwriter (Gemini/Groq) | 🟡 Stub + contract; templates ready |
| 4 | Voice (edge-tts) | 🟡 Stub + contract |
| 5 | Visuals (Pexels/Pixabay) | 🟡 Stub + contract |
| 6 | Assembly (FFmpeg) | 🟡 Stub + contract |
| 7 | Subtitles (faster-whisper) | 🟡 Stub + contract |
| 9 | Publish (YouTube) | 🟡 Stub + contract |
| — | `config.py` / `db.py` / `llm.py` | config ✅ · **db ✅ (integration-tested)** · llm 🟡 stub |

Legend: ✅ done · 🟡 scaffolded (stub/contract) · ⬜ not started

## Next actions

- ✅ **All credentials collected + verified** (Supabase secret key + YouTube OAuth done).
1. **Build the pipeline module-by-module** (rule 7): `db.py` ✅ → **`llm.py`** → `approval.py`
   → `ideation_fallback.py` → `scriptwriter.py` → `voice.py` → `visuals.py` → `assembly.py`
   → `subtitles.py` → `publish_youtube.py` → wire `production.py`.
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
