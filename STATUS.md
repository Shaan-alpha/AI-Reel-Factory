# STATUS — AI Reel Factory ("But It Matters")

> **Living progress log.** Every agent updates this before finishing a task
> (rule #1 in [CLAUDE.md](CLAUDE.md)). Keep it short, current, and honest.
> Newest entry at the top of the log.

**Phase:** 1 — MVP (4–5 captioned YouTube Shorts/day)
**Version:** 0.0.3 (pre-MVP — foundation + scaffolding + setup underway)
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
| Accounts & API keys | 🟡 Gemini ✅ · Groq ✅ · Supabase ✅* · Telegram ✅ · Pexels ✅ · YouTube ⬜ · Claude token ⬜ |
| YouTube handle `@butitmatters` | ✅ Secured (IG/TikTok not checked — Phase 3) |
| Pipeline logic (modules) | ⬜ Stubs only — not implemented |

\* Supabase key in `.env` is the **publishable** key — swap to the `sb_secret_…` key for server-side writes (see Next actions).

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
| — | `config.py` / `db.py` / `llm.py` | config ✅ · db/llm 🟡 stub |

Legend: ✅ done · 🟡 scaffolded (stub/contract) · ⬜ not started

## Next actions

1. **YouTube creds:** create the Google Cloud OAuth *Desktop app* (enable YouTube Data API v3,
   publish consent screen) → save `client_secret.json` → run `python tools/get_youtube_token.py`
   → paste `YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN` into `.env`.
2. **Supabase:** replace the publishable key with the `sb_secret_…` key (Project Settings →
   API Keys); run the 5-table SQL from [docs/03-setup-guide.md](docs/03-setup-guide.md) §4.
3. **Claude Routine auth:** run `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` (for ideation).
4. **GitHub Actions secrets:** mirror every `.env` value into the public repo's Actions secrets
   (`gh secret set …`) once the keys above are final.
5. Decide ideation runner: **Anthropic Routines** (recommended) vs Oracle VM cron.
6. Build **Module 1** first: create tables → implement `db.py` → test against Supabase →
   set up the Routine from `routines/ideation.md`. Then proceed module-by-module (rule 7):
   db → ideation → approval → scriptwriter → voice → visuals → assembly → subtitles →
   publish → wire `production.py`.
7. (Phase 3) Check `@butitmatters` on Instagram + TikTok before cross-posting.

## Open decisions

- **Ideation runner:** Anthropic Routines vs Oracle VM cron (lean Routines).

## Blockers

- _None._

---

## Log

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
