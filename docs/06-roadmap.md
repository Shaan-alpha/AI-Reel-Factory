# Roadmap — 5 Phases

From a reliable single-platform MVP to a multi-niche autonomous media machine.
Don't advance a phase until the previous one's exit criteria hold.

---

## Phase 1 — MVP ⭐ ✅ **BUILT & PUBLISHING LIVE** (exit criteria not met yet)
**Goal:** 4–5 **captioned** YouTube Shorts/day, fully automated except one Telegram tap.

- Ideation: **Gemini on Vertex** (`src/ideation_fallback.py`): a Groq story scout picks from Google
  News and Trends, grounded prose research, ≥ 2 live sources per idea. The Claude Routine
  (`routines/ideation.md`) is optional and has never run in production.
- Modules: Ideation → Approval (Telegram) → Scriptwriter → **Fact check** → Voice → Visuals →
  Assembly → **Subtitles (faster-whisper)** → Publish (YouTube), plus daily Analytics.
- **Shipped beyond MVP scope:** an independent **fact-check gate** (two samples, one repair, a
  strict hold when it cannot run); one near-human male **Gemini TTS** voice (Zubenelgenubi) with a
  same-voice fallback, then Chirp 3 HD, edge-tts and **Kokoro**; **AI-generated B-roll**
  (Cloudflare FLUX.2 klein + Ken Burns); **premium auto-editing** (crossfades, cinematic grade,
  AI-generated music beds with ducking, brand-logo bug, seamless loop); a frame-1 hook banner,
  key-point cards and an on-screen source; daily view analytics that feed ideation; a Telegram bot
  on Vercel (`/makeshort`, `/stats`, …); Template N, FFmpeg, Supabase, GitHub Actions, Vertex AI.
- **Trigger:** on demand only: `/makeshort N` in Telegram or the `make-short` workflow's Run
  button. The scheduled digests were removed on 2026-09-29 (GitHub started them 6.5–7 h late).
- **Exit:** 7 consecutive days of reliable auto-publishing with only approval taps. **Not met.**
  Gaps as of 2026-10-09:
  - **Cadence:** about 0.7 Shorts a day on average (about 81 public Shorts live), against 4–5.
  - **Trigger:** every run starts with `/makeshort` or a button press, then the taps; nothing
    publishes on its own. The exit criterion assumes a scheduled daily run and has not been
    restated for on-demand.
  - **Per-run cap:** 3 approvals and 3 reels a run (`APPROVAL_CAP`, `DAILY_REEL_CAP`), so 4–5 a
    day takes two runs.
  - **Reliability:** every reel from 2026-10-01 died at captions (a PyAV 19 release), so no Short
    shipped between 2026-09-28 and 2026-10-09, when it was fixed.
- **Model deadlines:** the Developer API shuts down both TTS models behind the channel voice on
  **2026-11-17**. Pick the `gemini-3.8-flash-tts` / `gemini-3.8-flash-lite-tts` successor by ear
  before then, or every reel moves to the billed Vertex path. Vertex retires `gemini-2.5-flash`,
  `-flash-lite` and `-pro` on **2026-10-20**; the pipeline no longer uses them.

See [02-implementation-plan.md](02-implementation-plan.md) for the step-by-step build and
[STATUS.md](../STATUS.md) for the live state.

---

## Phase 2 — Quality Upgrade
**Goal:** Reels look and sound premium.

- **Agent Debate** two-voice format (Kokoro already ships, as the last voice fallback)
- Auto thumbnails (Pillow/FFmpeg); today the frame-1 hook banner doubles as the in-feed thumbnail
- Beat-sync cutting + programmatic terminal/text B-roll
- **WhisperX** caption-timing upgrade (caption text already comes from the script; whisper only
  times the words)
- **Exit:** noticeably higher average retention vs Phase 1 baseline. (Retention is not measured
  yet; see Phase 4.)

---

## Phase 3 — Multi-Platform Expansion
**Goal:** Same reel, more platforms.

- Instagram Reels via Graph API (**after** Meta App Review — start early)
- TikTok via Content Posting API (**draft/semi-auto** until app audit clears)
- Cross-posting orchestration + per-platform metadata
- **Exit:** one approved idea fans out to YouTube + IG (+ TikTok draft) automatically.

---

## Phase 4 — AI Learning Loop
**Goal:** The system improves itself.

- *Already live from Phase 1:* `analytics.yml` snapshots each Short's views, likes and comments
  daily (YouTube Data API), and the best and worst recent titles feed the ideation prompt.
- Pull retention (YouTube Analytics API → `analytics`); the token first needs the
  `yt-analytics.readonly` re-auth
- Score hooks/templates in `hook_performance` (the table exists; nothing writes it yet)
- Feed top hooks and templates, not just titles, back into the ideation prompt
- Track best posting times
- **Exit:** ideation measurably favors proven hooks; retention trends up over weeks.

---

## Phase 5 — Multi-Page Scale
**Goal:** One infrastructure, many brands.

- Migrate heavy/always-on work to Oracle Free ARM VM + n8n
- Run multiple niches in parallel, each its own channel/page
- Centralized dashboard
- **Exit:** 2+ niches running simultaneously on shared infra, inside the cost cap (CLAUDE.md
  rule 2).

---

## Guiding rules (all phases)

1. Don't chase perfection early.
2. Hooks > visuals.
3. Retention > followers.
4. Consistency > cinematic quality.
5. Use templates, not pure randomness.
6. Analyze performance continuously.
7. Keep the human approval layer — AI still produces occasional cringe.
