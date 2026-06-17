# Roadmap — 5 Phases

From a reliable single-platform MVP to a multi-niche autonomous media machine.
Don't advance a phase until the previous one's exit criteria hold.

---

## Phase 1 — MVP ⭐ ✅ **BUILT & PUBLISHING LIVE** (v0.4.3)
**Goal:** 4–5 **captioned** YouTube Shorts/day, fully automated except one Telegram tap.

- Ideation: **Claude Code (Pro) via Anthropic Routine** (trend research) + free fallback (Gemini→Groq)
- Modules: Ideation → Approval → Scriptwriter → Voice → Visuals → Assembly →
  **Subtitles (faster-whisper)** → Publish(YouTube)
- **Shipped beyond MVP scope:** near-human **Google Chirp 3 HD** voice (fallback chain), **AI-generated
  B-roll** (Cloudflare Flux + Ken Burns), **premium auto-editing** (crossfade transitions, cinematic
  grade, music ducking, brand-logo bug, loop-friendly endings), Template N, FFmpeg, Supabase,
  GitHub Actions (on-demand + cron).
- **Exit:** 7 consecutive days of reliable auto-publishing with only approval taps. *(In progress — pipeline live.)*

See [02-implementation-plan.md](02-implementation-plan.md) for the step-by-step build.

---

## Phase 2 — Quality Upgrade
**Goal:** Reels look and sound premium.

- Kokoro TTS fallback + **Agent Debate** two-voice format
- Auto thumbnails (Pillow/FFmpeg)
- Beat-sync cutting + programmatic terminal/text B-roll
- **WhisperX** caption-accuracy upgrade
- **Exit:** noticeably higher average retention vs Phase 1 baseline.

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

- Pull metrics (YouTube Analytics API → `analytics`)
- Score hooks/templates in `hook_performance`
- Feed top performers back into Claude's ideation prompt
- Track best posting times
- **Exit:** ideation measurably favors proven hooks; retention trends up over weeks.

---

## Phase 5 — Multi-Page Scale
**Goal:** One infrastructure, many brands.

- Migrate heavy/always-on work to Oracle Free ARM VM + n8n
- Run multiple niches in parallel, each its own channel/page
- Centralized dashboard
- **Exit:** 2+ niches running simultaneously on shared infra at ~$0.

---

## Guiding rules (all phases)

1. Don't chase perfection early.
2. Hooks > visuals.
3. Retention > followers.
4. Consistency > cinematic quality.
5. Use templates, not pure randomness.
6. Analyze performance continuously.
7. Keep the human approval layer — AI still produces occasional cringe.
