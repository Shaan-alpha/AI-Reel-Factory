# Architecture & Data Flow

**Approach:** Serverless Batch + Claude-driven ideation. The daily **ideation** runs as an
**Anthropic Routine** (Claude Code, your Pro sub) that web-researches trends. The
deterministic production pipeline runs on scheduled **GitHub Actions**. State lives in
Supabase. Telegram is the only human touchpoint.
$0/month beyond Pro · no server to maintain · daily cron keeps Supabase awake.

---

## System diagram

```
        ┌────────────────────────────────────────────┐
 Daily  │  Anthropic Routine — Claude Code (Pro)      │
 08:00  │  web-research trends → 15–20 scored ideas   │
        │  fallback: Gemini/Groq if Pro limit/token   │
        └───────────────────────┬─────────────────────┘
                                 │ ideas → Supabase
                                 ▼
                  ┌─────────────────────────┐
                  │  Telegram Morning Digest │  ◄── ONLY human step
                  │  [✅ Approve] [❌ Reject] │
                  └────────────┬─────────────┘
                               │ 4–5 approved → Supabase queue
                               ▼
                 ┌───────────────────────────────────────┐
  GitHub Actions │  Production Pipeline:                  │
  cron (UTC,     │  script → voice → visuals → assemble → │
  staggered)     │  SUBTITLES → publish                   │
                 └───────────────────┬───────────────────┘
                                     │ post IDs → Supabase
                                     ▼
                 ┌───────────────────────────────────────┐
  cron next day  │  Analytics + Learning:                │
                 │  pull metrics → score hooks           │
                 └───────────────────┬───────────────────┘
                                     │ scores feed tomorrow's ideation
                                     └──────────────► (back to the Routine)
```

---

## Module → engine map

```
1 Ideation      → Claude Code (Pro) via Routine  [fallback: Gemini/Groq]
2 Approval      → Telegram Bot (inline buttons)
3 Scriptwriter  → Gemini/Groq + Templates A–D
4 Voice         → edge-tts (Kokoro fallback)
5 Visuals       → Pexels + Pixabay APIs
6 Assembly      → FFmpeg (1080×1920, Ken Burns)
7 Subtitles     → faster-whisper + FFmpeg burn-in      ★ MVP
8 Thumbnail     → Pillow / FFmpeg                       (Phase 2)
9 Publish       → YouTube Data API (auto); IG/TikTok (Phase 3)
10 Analytics    → YouTube Analytics API → Supabase      (Phase 4)
```

---

## Data flow (one reel's life)

```
Claude Routine: research trends ─► ideas (pending)
   └─approve─► ideas (approved)
        └─► scripts ──► [voice.wav] + [broll clips/]
              └─► assembled.mp4 ──► subtitles burned in ──► final.mp4
                    └─► YouTube upload ──► posts (published, videoId, url)
                          └─delete local .mp4 (asset policy)
                                └─next day─► analytics (views, retention, …)
                                      └─► hook_performance (scores)
                                            └─► feeds Claude's next ideation
```

---

## State, assets & boundaries

- **State:** Supabase Postgres — `ideas`, `scripts`, `posts`, `analytics`, `hook_performance`.
- **Assets:** render locally → upload → **delete local file**. Never store video in Supabase.
- **Secrets:** GitHub Actions secrets for the Python pipeline; the Routine holds its own
  (`CLAUDE_CODE_OAUTH_TOKEN`, Supabase URL/key). Local `.env` for dev only; never committed.
- **ToS boundary:** Claude is used **only** via official Claude Code / Routines. The OAuth
  token is never piped into custom Python. The free fallback uses Gemini/Groq developer APIs.
- **Timezone:** GitHub Actions cron is **UTC** — offset your 08:00 local accordingly.
```
