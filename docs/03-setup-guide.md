# Setup Guide — Accounts & API Keys

Do all of this **before** writing code. Collect every value into a local `.env` file
(never commit it). At the end you'll copy these into **GitHub → Settings → Secrets** so the
cron jobs can run headless.

> ⏱️ Budget ~1–2 hours. Instagram/TikTok items are **Phase 3** — skip for the MVP.

---

## 1. Claude Code (Pro) — primary ideation engine ★ required

You already have **Claude Pro**. This wires it into the pipeline the **ToS-compliant** way
(official Claude Code / Routines — *never* a raw OAuth token in custom scripts).

1. Install Claude Code (if not already): https://code.claude.com/docs
2. Run `claude setup-token` on a machine with a browser → log in with your Pro account.
3. Copy the generated token → save as `CLAUDE_CODE_OAUTH_TOKEN` (valid ~1 year — set a
   calendar reminder to regenerate).
4. **Routines** (for daily scheduling): https://www.infoq.com/news/2026/05/anthropic-routines-claude/
   — you'll create a Routine from `routines/ideation.md` at build time.
- Cost: included in your Pro sub. Usage is shared with your interactive Claude use, so keep
  ideation light (15–20 ideas/day is tiny).

---

## 2. Google AI Studio — Gemini API (free) ★ required (fallback + scripts)

1. Go to https://aistudio.google.com/ → sign in with Google.
2. **Get API key** → create key in a new project.
3. Save as `GEMINI_API_KEY`.
- Free tier: 1,500 req/day, 1M tokens/min. Used for scriptwriting + ideation fallback.

---

## 3. Groq — failover LLM (free) ★ required

1. Go to https://console.groq.com/ → sign up.
2. **API Keys** → create key.
3. Save as `GROQ_API_KEY`.
- Free tier: 14,400 req/day on Llama 3.1‑8B; limits stack per model.

---

## 4. Supabase — database (free) ★ required

1. Go to https://supabase.com/ → new project (region near you).
2. Save **Project URL** → `SUPABASE_URL` and the **service key** → `SUPABASE_KEY`.
3. Open **SQL Editor** and run the schema below.
- Free tier: 500 MB DB, 1 GB file storage, pauses after 7 idle days (cron keeps it awake).

```sql
-- Run this in Supabase SQL Editor

create table ideas (
  id bigint generated always as identity primary key,
  created_at timestamptz default now(),
  niche text,
  title text,
  hook text,
  angle text,
  est_score numeric,
  sources text[],                         -- source URLs (news niche: >=2 required)
  status text default 'pending'           -- pending | approved | rejected
);

create table scripts (
  id bigint generated always as identity primary key,
  idea_id bigint references ideas(id),
  template text,
  body text,
  caption text,
  hashtags text[],
  title text          -- the punchy PUBLISHED title; lets analytics learn winning title styles
);

create table posts (
  id bigint generated always as identity primary key,
  script_id bigint references scripts(id),
  platform text,                          -- youtube | instagram | tiktok
  external_id text,
  url text,
  status text,                            -- queued | published | failed
  published_at timestamptz
);

create table analytics (
  id bigint generated always as identity primary key,
  post_id bigint references posts(id),
  pulled_at timestamptz default now(),
  views int, retention numeric, likes int,
  comments int, shares int, saves int
);

create table hook_performance (
  id bigint generated always as identity primary key,
  hook_text text,
  niche text,
  uses int default 0,
  avg_retention numeric,
  avg_views numeric
);
```

> The Claude Routine needs to write to Supabase. At build time, give it access via the
> Supabase REST endpoint (URL + service key) — keep that key in the Routine's secrets, not in code.

---

## 5. Telegram Bot — approval UI (free) ★ required

1. In Telegram, message **@BotFather** → `/newbot` → follow prompts.
2. Save the token → `TELEGRAM_BOT_TOKEN`.
3. Message your new bot once, then get your chat ID:
   visit `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `chat.id`.
4. Save → `TELEGRAM_CHAT_ID`.

---

## 6. Pexels API — stock B-roll (free) ★ required

1. Go to https://www.pexels.com/api/ → sign up → get key.
2. Save as `PEXELS_API_KEY`.
- Free, CC0, commercial use OK, no attribution.

## 6b. Pixabay API — backup B-roll (free) ★ recommended

1. Go to https://pixabay.com/api/docs/ → sign up → get key.
2. Save as `PIXABAY_API_KEY`.

---

## 7. faster-whisper — subtitles (free, local) ★ required (MVP)

- No account needed. `pip install faster-whisper`. First run downloads a model
  (use `base` or `small` for CPU speed). Produces the word-level timestamps for captions.

---

## 8. YouTube Data API v3 — publishing (free) ★ required

1. https://console.cloud.google.com/ → create/reuse a project.
2. **APIs & Services → Library** → enable **YouTube Data API v3**.
3. **OAuth consent screen** → External, add your email as test user, add scope
   `https://www.googleapis.com/auth/youtube.upload`.
4. **Credentials → Create → OAuth client ID → Desktop app** → download `client_secret.json`.
5. One-time local auth → generate a **refresh token**; store `YOUTUBE_REFRESH_TOKEN`
   (+ `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`).
- ~100 uploads/day on free quota. Publish the consent screen so the token doesn't expire.

---

## 9. GitHub — orchestration (free) ★ required

1. Create a repo (private fine).
2. **Settings → Secrets and variables → Actions → New repository secret** for every key.
3. Actions cron runs in **UTC** — convert your local 8 AM accordingly.

---

## 10. Instagram + TikTok — Phase 3 only (skip for MVP)

- **Instagram:** Business/Creator account + Facebook Page + Meta Developer App with
  `instagram_business_content_publish`, then **Meta App Review** (days–weeks). Start early.
- **TikTok:** Content Posting API **Direct Post** needs a full app audit (2–6 weeks);
  until audited, posts are private-only → draft/semi-auto.

---

## ✅ `.env` checklist (Phase 1)

```env
# Ideation (primary = Claude Code / Routine)
CLAUDE_CODE_OAUTH_TOKEN=

# LLM (scripts + ideation fallback)
GEMINI_API_KEY=
GROQ_API_KEY=

# Database
SUPABASE_URL=
SUPABASE_KEY=

# Approval
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Visuals
PEXELS_API_KEY=
PIXABAY_API_KEY=

# YouTube publishing
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
YOUTUBE_REFRESH_TOKEN=

# Config
CHANNEL_NAME=But It Matters     # brand name (also used in disclosure/branding)
NICHE=impact-news         # daily impact news/info explainers (India + world)
NICHE_LEAN=soft-positive  # science/tech/economy/breakthroughs; avoid partisan/communal
CONTENT_STYLE=daily-impact-explainer   # what happened -> why it matters -> impact
DIGEST_HOUR_UTC=02        # 08:00 IST ≈ 02:30 UTC (adjust to your timezone)
ENABLE_FALLBACK_IDEATION=true   # use Gemini/Groq only if Claude didn't produce ideas
AI_DISCLOSURE=true        # set YouTube altered/synthetic flag + disclosure line on upload
MIN_SOURCES=2             # min independent sources before an idea becomes a reel
```

> Copy each into GitHub Actions secrets (and the Routine's secrets where relevant).
> Commit only `.env.example` (blank values).
