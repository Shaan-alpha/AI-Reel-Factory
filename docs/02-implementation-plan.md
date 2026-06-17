# Phase 1 — MVP Implementation Plan

> ✅ **STATUS: BUILT & PUBLISHING LIVE** (v0.4.3) — every module below is done, tested, and
> shipping captioned Shorts to **[@butitmatters](https://youtube.com/@butitmatters)**. The
> checklist in this doc is the **original build guide** (kept as a historical record of the
> step-by-step path); the live state of the system is in **[STATUS.md](../STATUS.md)** and the
> shipped features are in **[CHANGELOG.md](../CHANGELOG.md)**. Several modules shipped *beyond*
> this plan's MVP scope — near-human **Google Chirp 3 HD** voice, **AI-generated B-roll**
> (Cloudflare Flux + Ken Burns), and **premium auto-editing** (transitions, cinematic grade,
> music ducking, brand-logo bug, loop-friendly endings).

**Goal:** Reliably publish **4–5 captioned YouTube Shorts per day**, fully automated except
for one Telegram approval tap. Template N (news-impact). YouTube only. Claude-driven
ideation. **Word-by-word subtitles included.**

> Build **module by module, in order**. Get each one working and tested in isolation
> before starting the next. Do not wire everything together until the modules each work alone.

---

## 0. Project scaffolding

```
ai-reel-factory/
├── .github/workflows/
│   ├── production.yml         # cron: staggered → render + publish approved ideas
│   └── analytics.yml          # cron: next-day → pull metrics (Phase 4)
├── routines/
│   └── ideation.md            # Claude Routine prompt: research trends → ideas → Supabase
├── src/
│   ├── config.py              # loads env vars / secrets
│   ├── db.py                  # Supabase client + table helpers
│   ├── llm.py                 # Gemini primary, Groq failover (FALLBACK ideation + scripts)
│   ├── ideation_fallback.py   # Module 1 fallback (only if Claude unavailable)
│   ├── approval.py            # Module 2 (Telegram bot + buttons)
│   ├── scriptwriter.py        # Module 3
│   ├── voice.py               # Module 4
│   ├── visuals.py             # Module 5
│   ├── assembly.py            # Module 6 (FFmpeg)
│   ├── subtitles.py           # Module 7 (faster-whisper + FFmpeg burn-in)
│   └── publish_youtube.py     # Module 9 (YouTube only for MVP)
├── templates/                 # prompt templates A–D
├── tests/
├── requirements.txt
├── .env.example
└── README.md
```

**Tasks**
- [ ] `python -m venv venv` + `requirements.txt` (google-generativeai, groq, supabase,
      python-telegram-bot, edge-tts, ffmpeg-python, faster-whisper,
      google-api-python-client, requests, python-dotenv)
- [ ] Install **Claude Code** + run `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN`
- [ ] `.env.example` listing every secret (see setup guide)
- [ ] `config.py` reads env vars, fails loudly if any required key is missing
- [ ] Push repo to GitHub (private fine; cron works on private with 2,000 free min/mo)

---

## 1. Database layer (`db.py`)

- [ ] Create the 5 tables in Supabase (SQL in setup guide)
- [ ] Helpers: `insert_ideas()`, `get_pending_ideas()`, `set_idea_status()`,
      `get_approved_ideas()`, `insert_script()`, `insert_post()`
- [ ] **Test:** insert a dummy idea, read it back, update status. Confirm in Supabase UI.

---

## 2. Module 1 — Ideation (Claude Routine + fallback)

**Niche = impact-news.** See [08-news-niche-playbook.md](08-news-niche-playbook.md) — read
it before writing the Routine. Originality, sourcing, and the sensitivity filter are baked in here.

**Primary: Claude Code via Anthropic Routine.**
- [ ] Write `routines/ideation.md`: instruct Claude to (a) **web-research today's
      developments** in the impact-news lane (India + world, soft/positive-impact lean),
      (b) **prefer high-impact, under-covered angles** over headlines everyone ran (originality),
      (c) capture **≥2 source URLs per idea** (`MIN_SOURCES`), (d) **apply the sensitivity
      filter** (exclude communal/partisan/unverified-election/graphic topics), (e) generate
      **15–20 ideas** as JSON `{title, hook, angle, est_score, sources[]}`, (f) read top hooks
      from `hook_performance`, (g) **insert rows into Supabase** with status `pending`.
- [ ] Configure the Routine to run daily ~08:00 local (Routines handles scheduling; this
      sidesteps the GitHub-Actions cron auth bug).
- [ ] Auth: `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`.

**Fallback: free APIs (opt-in, off by default).**
- [ ] `ideation_fallback.py`: same JSON contract via Gemini→Groq (uses `llm.py`).
- [ ] Trigger only if the Routine didn't write today's ideas (e.g. production workflow checks
      Supabase; if empty, run fallback) — so a Pro cap/token lapse never kills the digest.
- [ ] **Test:** run the Routine once → 15–20 rows land in Supabase; then simulate "no ideas"
      and confirm the fallback fills them.

> ToS note: ideation runs **only** via official Claude Code / Routines. Never pipe the OAuth
> token into custom Python. The fallback uses the free Gemini/Groq **developer APIs**, not Claude.

---

## 3. Module 2 — Approval (`approval.py`)

- [ ] Telegram bot: send the day's pending ideas as a **Morning Digest** — one message per
      idea (or paginated) with inline **[✅ Approve]** / **[❌ Reject]** buttons
- [ ] Button callback writes status to `ideas` (`approved`/`rejected`)
- [ ] Soft cap at 4–5 approvals to protect daily volume
- [ ] MVP: **polling** for button clicks (a short script run by the production workflow);
      webhook is a later nicety
- [ ] **Test:** trigger digest to your chat, tap approve, confirm DB updates

---

## 4. Module 3 — Scriptwriter (`scriptwriter.py`)

> **Originality is the monetization gate** (YouTube 2026 Inauthentic Content policy).
> The script's core value is **analysis**, not a summary. See [08-news-niche-playbook.md](08-news-niche-playbook.md) §1.

- [ ] Input: an approved idea (incl. its `sources`) + **Template N** prompt
- [ ] Output: `{script_body, caption, hashtags[]}` — ≤60s Short (~130–150 words), 3-sec hook
- [ ] Structure (Template N): hook → what happened (facts **in own words**) → **WHY IT
      MATTERS (original analysis)** → impact on you/India/world → CTA
- [ ] **Cite the source** in script + caption ("according to …"); neutral, factual framing
- [ ] Caption includes **source links + AI-disclosure line** (see Module 9)
- [ ] **SEO (where discoverability actually comes from):** generate a **keyword-rich title**
      front-loading the topic + intent (e.g. "ISRO's new mission, explained — why it matters")
      and 3–5 search-style hashtags/tags. The channel name (*But It Matters*) is only a minor signal;
      titles/descriptions/tags carry the search. Patterns that match volume: "X explained",
      "what … means", "why … matters", + India/world + year where relevant.
- [ ] Append `#Shorts` so YouTube classifies it correctly
- [ ] Engine: Gemini/Groq via `llm.py` (Claude optional later)
- [ ] Write to `scripts` table
- [ ] **Test:** feed one approved idea; confirm the script *analyzes* (not just summarizes)
      and cites the source; iterate the prompt

---

## 5. Module 4 — Voice (`voice.py`)

- [ ] `edge-tts` → narration `.wav`/`.mp3`; one clear voice for MVP
- [ ] Return audio path + measured duration
- [ ] Wrap in try/except so a future Kokoro fallback can slot in
- [ ] **Test:** generate narration from a sample script, listen, confirm <60s

---

## 6. Module 5 — Visuals (`visuals.py`)

> **Copyright safety (news niche):** stock B-roll only — **never broadcaster/agency footage**.
> Narration is the primary asset; clips are supporting. See [08-news-niche-playbook.md](08-news-niche-playbook.md) §3.

- [ ] Extract 3–6 keywords from the script
- [ ] Query **Pexels** (then Pixabay backup) for vertical clips per keyword (CC0 only)
- [ ] Prefer **maps / charts / data-viz** for impact stories (safer + more relevant)
- [ ] Download enough clips to cover narration duration; cache to temp dir
- [ ] **High edit density:** plan a cut every **5–8s** (handled in assembly) — retention + copy-safety
- [ ] **Test:** given keywords, confirm valid CC0 clips download

---

## 7. Module 6 — Assembly (`assembly.py`, FFmpeg)

- [ ] Concat/trim B-roll to narration length, scaled/cropped to **1080×1920**
- [ ] Overlay narration; light Ken Burns (slow zoom/pan)
- [ ] Optional faint royalty-free music bed
- [ ] Export `.mp4` (H.264, ≤60s, 9:16) — **no captions yet; subtitles added next**
- [ ] **Test:** produce one complete watchable (un-captioned) reel end-to-end

---

## 8. Module 7 — Subtitles (`subtitles.py`) ★ in MVP

- [ ] Run **faster-whisper** on the narration audio → word-level timestamps
- [ ] Generate karaoke-style word-by-word caption events
- [ ] Burn captions into the video with **FFmpeg** (pixel-baked so they survive re-uploads)
- [ ] Style: large, centered/lower-third, bold, high-contrast with outline
- [ ] **Test:** captions appear word-synced and readable on a phone screen

---

## 9. Module 9 — Publish to YouTube (`publish_youtube.py`)

> **AI disclosure (news niche):** set the altered/synthetic-content flag + disclosure line.
> See [08-news-niche-playbook.md](08-news-niche-playbook.md) §2.

- [ ] OAuth2 once locally → store refresh token as a GitHub secret (headless cron upload)
- [ ] `videos.insert` with title (+`#Shorts`), description, tags, category, privacy
- [ ] **Set the "altered or synthetic content" disclosure** (`AI_DISCLOSURE=true`)
- [ ] Description includes **source links + disclosure line** ("Narration is AI-generated;
      visuals are stock/illustrative; sources above")
- [ ] Save returned `videoId` + URL to `posts`
- [ ] **Delete the local .mp4 after upload** (asset policy)
- [ ] **Test:** upload one unlisted Short, confirm it's classified as a Short and the
      disclosure label is set

---

## 10. Wire the pipeline + schedule

- [ ] `production.py` orchestrator: for each approved idea →
      script → voice → visuals → assemble → **subtitle** → publish → record → cleanup
- [ ] On run, **check Supabase for today's ideas**; if empty, fire the fallback ideation
- [ ] `production.yml`: cron staggered through the day (spread 4–5 posts), in **UTC**
- [ ] Claude **Routine** handles the morning ideation independently
- [ ] All secrets in **GitHub → Settings → Secrets and variables → Actions**
- [ ] **Test (the real one):** a full unattended day after you approve — 4–5 captioned Shorts go live

---

## ✅ Phase-1 Definition of Done

- A real morning digest (Claude-researched ideas) arrives in Telegram.
- You approve 4–5 with taps and do nothing else.
- 4–5 **captioned** YouTube Shorts publish automatically that day.
- It repeats reliably for **7 consecutive days** with zero manual steps beyond approvals.

When that holds → [06-roadmap.md](06-roadmap.md) Phase 2 (thumbnails, Kokoro/debate voices,
beat-sync, WhisperX upgrade).

---

## ⚠️ Gotchas to remember

- **Claude ideation runs via official Routines/Claude Code only** — never pipe the OAuth
  token into custom Python (ToS). The free-API fallback uses Gemini/Groq developer APIs.
- **Claude Pro limits are shared** with your interactive coding usage — ideation is light,
  but the fallback exists for the day you hit a cap.
- **`CLAUDE_CODE_OAUTH_TOKEN` expires ~yearly** — set a reminder to re-run `claude setup-token`.
- **GitHub Actions is UTC-only** — convert 8 AM local to the right UTC cron.
- **Supabase free projects pause after 7 idle days** — the daily cron keeps it warm.
- **YouTube OAuth refresh tokens** can expire in "Testing" mode — publish the consent screen.
- **edge-tts is unofficial** — Kokoro fallback (Phase 2) is the fix if it breaks.
- **Keep secrets out of git** — only `.env.example` (no real keys) gets committed.
