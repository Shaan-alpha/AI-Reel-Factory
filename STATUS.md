# STATUS — AI Reel Factory ("Newsence")

> **Living progress log.** Every agent updates this before finishing a task
> (rule #1 in [CLAUDE.md](CLAUDE.md)). Keep it short, current, and honest.
> Newest entry at the top of the log.

**Phase:** 1 — MVP (4–5 captioned YouTube Shorts/day)
**Version:** 0.0.1 (pre-MVP — foundation)
**Last updated:** 2026-06-05

---

## Snapshot

| Area | State |
|------|-------|
| Design / docs | ✅ Complete — 8 docs in [docs/](docs/) |
| Project rules | ✅ Written — [CLAUDE.md](CLAUDE.md) |
| Accounts & API keys | ⬜ Not started — see [docs/03-setup-guide.md](docs/03-setup-guide.md) |
| `@newsence` handle check (YT/IG/TT) | ⬜ Not verified |
| Scaffolding (src/, routines/, tests/) | ⬜ Not started |
| Pipeline code | ⬜ Not started |

## Module progress (Phase 1)

| # | Module | Status |
|---|--------|--------|
| 1 | Ideation (Claude Routine + fallback) | ⬜ Not started |
| 2 | Approval (Telegram) | ⬜ Not started |
| 3 | Scriptwriter (Gemini/Groq) | ⬜ Not started |
| 4 | Voice (edge-tts) | ⬜ Not started |
| 5 | Visuals (Pexels/Pixabay) | ⬜ Not started |
| 6 | Assembly (FFmpeg) | ⬜ Not started |
| 7 | Subtitles (faster-whisper) | ⬜ Not started |
| 9 | Publish (YouTube) | ⬜ Not started |

## Next actions

1. Decide ideation runner: **Anthropic Routines** (recommended) vs Oracle VM cron.
2. Work through [docs/03-setup-guide.md](docs/03-setup-guide.md) — create accounts, run
   `claude setup-token`, collect API keys into a local `.env`.
3. Verify `@newsence` handle is free on YouTube + Instagram + TikTok.
4. Scaffold the repo (`src/`, `routines/`, `tests/`, `requirements.txt`, `.env.example`).
5. Build Module 1 (ideation) first; test in isolation before Module 2.

## Open decisions

- **Ideation runner:** Anthropic Routines vs Oracle VM cron (lean Routines).

## Blockers

- _None._

---

## Log

### 2026-06-05 — Foundation set up
- Imported the 8-doc design package into [docs/](docs/) from the `AI Idea` source folder.
- Wrote [CLAUDE.md](CLAUDE.md): 18 operating rules (docs-as-memory, free-first, no
  self-attribution, ToS boundary, news compliance, runtime reliability, versioning).
- Added this STATUS.md, [README.md](README.md), and [CHANGELOG.md](CHANGELOG.md).
- No pipeline code yet — foundation only by design.
