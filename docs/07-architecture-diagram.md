# Architecture & Data Flow

> **As built**, checked against the code on 2026-10-09. The original design (a daily Claude
> Routine and staggered crons) is recorded in [01-design-spec.md](01-design-spec.md) §4.
> Current state: [STATUS.md](../STATUS.md); operating rules: [CLAUDE.md](../CLAUDE.md).

**Approach:** Serverless batch, **run on demand**. The operator asks for Shorts from Telegram
(`/makeshort N`) or with the `make-short` workflow's Run button; one GitHub Actions job then
proposes ideas, waits for the approval taps and produces the approved reels. Ideation, the
script and the fact check run on **Gemini through Vertex AI**, with Groq as the free failover
for ungrounded calls. State lives in Supabase. A small webhook bot on **Vercel** starts runs and
records the taps, so the operator can do everything from Telegram: start a run, approve, get the link.
≤ $5/month beyond Pro (Vertex AI and Cloud Text-to-Speech are billed; everything else is free
tier) · no server to maintain · the daily analytics job keeps Supabase awake.

---

## System diagram

```
        /makeshort N in Telegram                     "Run workflow" button
                    │                                          │
                    ▼                                          │
 ┌────────────────────────────────────┐                        │
 │ Telegram bot (Vercel webhook)      │                        │
 │ telegram-bot/api/telegram.py       │                        │
 └──────────────────┬─────────────────┘                        │
                    │ workflow_dispatch (GH_PAT)               │
 ┌──────────────────▼──────────────────────────────────────────▼──────┐
 │ GitHub Actions: make-short.yml → python -m src.production make     │
 │ ubuntu-24.04 · one run at a time · 90-min job                      │
 │ YouTube token pre-flight · release leftover approvals ·            │
 │ age out stale pending ideas                                        │
 │ Ideation: Google News + Trends RSS → Groq picks N stories →        │
 │ Gemini (Vertex AI, grounded search) researches them →              │
 │ ideas (pending, ≥ 2 sources each)                                  │
 └──────────────────────────────────┬─────────────────────────────────┘
                                    │ digest
                                    ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │ Telegram digest: [Approve] [Reject] [Pass]   ◄── ONLY human step   │
 │ each tap → Telegram → Vercel bot → Supabase ideas.status           │
 └──────────────────────────────────┬─────────────────────────────────┘
                                    │ the run polls Supabase until every idea is decided,
                                    │ 3 are approved, or wait_min runs out
                                    ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │ Same job, for each approved idea:                                  │
 │ script → FACT-CHECK GATE → voice → visuals → assembly →            │
 │ captions → YouTube upload → posts row → link on Telegram           │
 │ gate blocks → idea 'blocked'; other failure → back to 'pending';   │
 │ either way a Telegram alert                                        │
 └──────────────────────────────────┬─────────────────────────────────┘
                                    │ post IDs → Supabase
                                    ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │ analytics.yml (daily, scheduled): views, likes, comments →         │
 │ Supabase analytics; removed Shorts reported on Telegram            │
 └──────────────────────────────────┬─────────────────────────────────┘
                                    │ recent winners + low performers
                                    └──────────► the next run's ideation prompt
```

A bare `/makeshort` asks for 5 ideas (1–8 allowed) and waits up to 30 minutes for taps; the Run
button defaults to 3 ideas and 20 minutes. The wait is cut short when the 90-minute job would
otherwise run out before a reel fits. Ideas still pending from an earlier run join the digest.
Only `tests.yml` and `analytics.yml` run on a schedule; `production.yml`
(`python -m src.production`) is an optional, manual-only path.

---

## Module → engine map

```
1  Ideation      → Google News RSS (India front page + World, Business, Technology, Science) and
                   Google Trends RSS (IN), plus recent winners → Groq picks N distinct stories →
                   Gemini on Vertex researches them in prose with grounded search → JSON ideas
                   with ≥ 2 live sources, deduplicated against the last 10 days
                   (a Claude Routine, routines/ideation.md, is optional and has never run)
2  Approval      → Telegram digest (Approve / Reject / Pass); the Vercel bot writes each tap to
                   Supabase; at most 3 approvals per run (APPROVAL_CAP)
3  Scriptwriter  → Template N (25–30 s, 80-word cap, hook-judge punch-up); grounded write on
                   Gemini (Vertex), Groq failover; source links + disclosure line added in code
11 Fact check    → Gemini on Vertex with grounded search, 2 samples; blocks fabrication, waives
                   imprecision; one repair pass, then a re-check; runs BEFORE the voice
4  Voice         → Gemini TTS, voice Zubenelgenubi: Developer API → Vertex → the 2.5 models (same
                   voice) → Chirp 3 HD → edge-tts en-IN-PrabhatNeural → Kokoro am_michael
5  Visuals       → VISUAL_SOURCE=ai: Cloudflare Workers AI FLUX.2 klein → FLUX.1 schnell, else a
                   Pexels photo (Ken Burns on both) → Pexels/Pixabay stock video (not CC0)
6  Assembly      → FFmpeg 1080×1920 H.264 — crossfades · grade · vignette · music bed + ducking ·
                   a click every 2nd cut · -14 LUFS · brand-logo bug · loop-friendly ending
                   (all toggle-gated, fail-soft)
7  Subtitles     → faster-whisper (base) word timings, caption text from the approved script —
                   karaoke + frame-1 hook + key-point cards + "Source:" lower-third (libass)
8  Thumbnail     → Pillow / FFmpeg                                              (Phase 2)
9  Publish       → YouTube Data API videos.insert (containsSyntheticMedia + disclosure line);
                   IG/TikTok                                                    (Phase 3)
10 Analytics     → daily YouTube Data API view snapshots → Supabase; recent winners and low
                   performers feed ideation; hook/template scoring              (Phase 4)
```

### Models (CI defaults on 2026-10-09)

| Use | Setting | Default |
|---|---|---|
| Ideation research (grounded, prose) | `IDEATION_MODEL` | `gemini-3.5-flash-lite` → `gemini-3.5-flash` |
| Ideas JSON; ungrounded script and repair fallbacks | `GEMINI_MODEL` | `gemini-3.8-flash` |
| Grounded script write and repair | `GEMINI_GROUNDED_MODEL` | `gemini-3.5-flash-lite` → `gemini-3.5-flash` |
| Fact check (grounded) | `FACTCHECK_MODEL` | `gemini-3.5-flash` → `gemini-3.5-flash-lite` |
| Story selection, hook punch-up, tighten pass, keywords (Groq first); failover for every other ungrounded call | `GROQ_MODEL` | `openai/gpt-oss-120b` |
| Narration | `GEMINI_TTS_MODEL` · `GEMINI_TTS_VOICE` | `gemini-3.1-flash-tts-preview` · `Zubenelgenubi` |

The Gemini text models run on Vertex AI in CI (`GEMINI_USE_VERTEX=true`). A comma-separated
setting is an ordered chain: a model the backend no longer serves moves the call down the chain.
Grounded calls are Gemini-only, because Groq has no grounded search. The Developer API shuts
down both of its TTS models on 2026-11-17; see STATUS.md for the replacement plan.

---

## Data flow (one reel's life)

```
trigger   /makeshort N → Vercel bot → workflow_dispatch   (or the Run button)
ideas     RSS stories → Groq picks N → Gemini (Vertex, grounded) researches them
          → ideas (pending, ≥ 2 sources) → Telegram digest
approve   tap → Telegram → Vercel bot → ideas.status = approved / rejected / passed
          (untapped when the wait ends → passed; pending over 24 h → passed by the next run)
script    → scripts (body, caption, hashtags, title)
gate      fact check → pass: continue
                     → block: one repair + re-check → still blocked: ideas.status = blocked,
                       Telegram alert, stop
          verdict → scripts.factcheck
media     narration.wav (Gemini TTS, Zubenelgenubi) + AI images / stock clips
          → reel_raw.mp4 (grade · music bed · ducking · logo · loop)
          → captions + hook banner + key-point cards + "Source:" → reel_final.mp4
publish   → YouTube (synthetic-content flag) → posts (published, external_id, url, voice)
          → ideas.status = produced → "✅ Published <link>" on Telegram
          → local files deleted (asset policy)
learn     daily → analytics (views, likes, comments) → recent winners + low performers
          → the next run's ideation prompt
          (hook_performance exists, but nothing reads or writes it)
```

---

## State, assets & boundaries

- **State:** Supabase Postgres — `ideas`, `scripts`, `posts`, `analytics` (and
  `hook_performance`, unused). RLS on; the pipeline writes with the server-side `sb_secret_` key.
- **Assets:** render locally → upload → **delete local file**. Never store video in Supabase.
- **Secrets:** GitHub Actions secrets for the pipeline. Vertex AI is reached keylessly through
  Workload Identity Federation in CI (no service-account key is stored) and ADC locally. The bot
  has its own environment on Vercel (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `WEBHOOK_SECRET`,
  `GH_PAT`, `GH_REPO`, `SUPABASE_URL`, `SUPABASE_KEY`). Local `.env` for dev only; never committed.
- **Triggers:** on demand only. Scheduled: `tests.yml` (daily, plus every push to `main` and
  every PR) and `analytics.yml` (daily); GitHub starts both hours late, which does not matter
  for them. `analytics.yml` also re-enables the scheduled workflows, which GitHub disables after
  60 days without a commit.
- **Telegram bot:** a stdlib Python function on Vercel (Hobby), project `telegram-bot` in team
  `shaan-alphas-projects`, webhook `telegram-bot-gilt-omega.vercel.app/api/telegram`. It serves
  only the operator's chat and fails closed without `WEBHOOK_SECRET` and `TELEGRAM_CHAT_ID`.
  CLI-deployed, not git-connected: every change needs `vercel deploy --prod` from `telegram-bot/`.
- **ToS boundary:** Claude is used **only** via official Claude Code / Routines, and none runs
  today. The OAuth token is never piped into custom Python; the pipeline uses Gemini and Groq.
- **Runner:** `ubuntu-24.04`, pinned because `ubuntu-latest` moves to 26.04 from 2026-10-19;
  Python 3.12; FFmpeg from apt. One pipeline run at a time (the `reel-pipeline` concurrency group).
- **Timezone:** Actions runs in **UTC**; the operator, and the bot's `/today`, use IST.
