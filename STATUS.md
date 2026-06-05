# STATUS — AI Reel Factory ("Newsence")

> **Living progress log.** Every agent updates this before finishing a task
> (rule #1 in [CLAUDE.md](CLAUDE.md)). Keep it short, current, and honest.
> Newest entry at the top of the log.

**Phase:** 1 — MVP (4–5 captioned YouTube Shorts/day)
**Version:** 0.0.2 (pre-MVP — foundation + scaffolding)
**Last updated:** 2026-06-05

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
| Accounts & API keys | ⬜ Not started — see [docs/03-setup-guide.md](docs/03-setup-guide.md) |
| `@newsence` handle check (YT/IG/TT) | ⬜ Not verified |
| Pipeline logic (modules) | ⬜ Stubs only — not implemented |

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

1. Decide ideation runner: **Anthropic Routines** (recommended) vs Oracle VM cron.
2. Work through [docs/03-setup-guide.md](docs/03-setup-guide.md) — create accounts, run
   `claude setup-token`, collect API keys into a local `.env`.
3. Verify `@newsence` handle is free on YouTube + Instagram + TikTok.
4. Build **Module 1** first: create the 5 Supabase tables → implement `db.py` → test against
   Supabase → set up the Anthropic Routine from `routines/ideation.md`.
5. Then proceed module-by-module (rule 7): db → ideation → approval → scriptwriter → voice →
   visuals → assembly → subtitles → publish → wire `production.py`.

## Open decisions

- **Ideation runner:** Anthropic Routines vs Oracle VM cron (lean Routines).

## Blockers

- _None._

---

## Log

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
