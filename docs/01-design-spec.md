# AI Reel Factory — Design Specification

**Date:** 2026-05-31
**Status:** Approved (design phase)
**Owner:** Shaan Satsangi
**Channel:** Newsence (daily impact news/info explainers, India + world)

---

## 1. Vision & Primary Goal

Build a **near-zero-cost autonomous AI content system** that generates ideas, writes
scripts, narrates, assembles vertical video, captions, and publishes — requiring exactly
**one human action per day**: approving 4–5 of ~15–20 generated ideas via a Telegram
"Morning Digest."

> **Primary goal (in priority order):** Reliably produce and publish **4–5 automated
> reels per day**. Consistency beats sophistication. Do not chase perfection early.

The operator acts as the *creative director* of an autonomous media machine.

---

## 2. Decisions That Anchor This Design

These were confirmed with the operator and drive every downstream choice:

| Decision | Choice | Consequence |
|----------|--------|-------------|
| Operator skill | **Can code (Python)** | Custom Python pipeline, no no-code lock-in |
| Publishing posture | **Official APIs + semi-auto** | Auto where sanctioned; manual tap where ToS-risky |
| First platform | **YouTube Shorts** | Only platform with free, ToS-safe full automation |
| Runtime | **Cloud / always-on** | GitHub Actions cron; PC-independent reliability |
| **Ideation engine** | **Claude Code (Pro) via Anthropic Routines** | Claude researches trends + generates ideas daily; free APIs are an opt-in safety-net fallback |
| **Ideation runner** | **Anthropic Routines (cloud)** | Scheduled in Anthropic's cloud; laptop can be off; sidesteps the GH-Actions cron auth bug |
| **Subtitles** | **In MVP (Phase 1)** | Word-by-word captions from day one (retention driver) |
| **Niche** | **Daily impact news/info explainers** (India + world), soft/positive lean | Claude researches the day's high-impact developments; explainer format; triggers news-specific compliance rules — see §3a + [08-news-niche-playbook.md](08-news-niche-playbook.md) |
| **Content style** | **Daily impact explainer** (what happened → why it matters → impact) | Batches into the morning-digest cadence; maximizes monetization-safe originality |

---

## 3. Key 2026 Research Findings (and how they shape the build)

1. **YouTube upload quota collapse (the big unlock).** As of **2025-12-04**, `videos.insert`
   dropped from ~1,600 to **~100 quota units**. The free 10,000 units/day now permits
   **~100 Shorts uploads/day** — full automation is comfortably free and ToS-compliant.
2. **Claude Pro is NOT an API — but official Claude Code automation IS sanctioned.**
   Claude Pro subscribes you to the Claude apps (claude.ai, desktop, **Claude Code**), not
   the developer API. Anthropic explicitly **bans piping a Pro/Max OAuth token into custom
   scripts or the Agent SDK** (ToS violation). However, running **official Claude Code
   headless** (`claude -p`) or via **Anthropic Routines** (cloud-scheduled Claude Code) is
   *built for scripted/automated use* and exempt — for "ordinary individual usage," which a
   personal 5-reel/day pipeline is. Auth via `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN`
   (Pro/Max, ~1-year validity). Claude's built-in web search does the trend research.
3. **Routines run on your Pro plan, in the cloud — with caveats.** Available in research
   preview to Pro/Max/Team/Enterprise; execute on Anthropic-managed infra (laptop can be
   off); support scheduled + API + GitHub triggers. **Caveats:** daily run caps scale by
   plan, and it's a *research preview* (limits/API may change) — which is exactly why the
   free fallback below is mandatory, not optional.
4. **Pro usage is ample for ideation.** ~60 Sonnet hrs/week (post-May-2026 increase),
   peak-hour throttling removed. Generating ~20 ideas/day is a tiny slice. Usage is shared
   across claude.ai / Desktop / Code, so the fallback covers the rare day a cap is hit.
5. **Free LLMs as the fallback safety-net.** Gemini free: 1,500 req/day, 1M tokens/min.
   Groq free: 14,400 req/day on Llama 3.1‑8B, 1,000/day on Llama 3.3‑70B, per-model limits.
   Fires only if a Routine cap is hit or the token lapses, so the digest never fails.
6. **TTS resilience.** `edge-tts` is free but *unofficial* and can break without notice.
   Add **Kokoro TTS** (Apache‑2.0, 82M params, CPU-capable, 54 voices) as a fallback and as
   the engine for the two-voice "Agent Debate" format (Phase 2).
7. **Subtitles (now MVP).** **faster-whisper** (CPU-friendly, word timestamps) is the
   default for karaoke word-by-word captions; **WhisperX** is the higher-accuracy upgrade.
8. **Generative video is not MVP-ready at daily volume.** Free Veo/Runway tiers are
   rate-capped and unreliable. MVP relies on **stock B-roll (Pexels + Pixabay APIs, CC0,
   free for commercial use)** plus Ken Burns motion. Generative video is a later garnish.
9. **Hosting.** **GitHub Actions cron** is the best free runner for the deterministic Python
   pipeline (unlimited minutes on public repos; ~2,000/mo private; runs in **UTC**).
   Anthropic **Routines** handles the Claude ideation step (sidesteps the known
   `claude-code-action` cron auth bug). Oracle Always-Free ARM VM is reserved for Phase 5
   (note: Indian debit cards often fail Oracle signup — don't depend on it for MVP).
10. **Don't reinvent the wheel.** Mature open-source faceless pipelines (ShortGPT,
    SamurAIGPT/AI-Youtube-Shorts-Generator, SaarD00 AutoShorts) are referenced for patterns.
11. **Platform automation honesty.** YouTube = full auto. Instagram = real Graph API but
    needs Business/Creator account + FB Page + **Meta App Review**, capped ~25–50 posts/24h.
    TikTok Direct Post needs a **full app audit (2–6 weeks)**; until audited, API posts are
    private-only → **TikTok = render + push-to-draft, operator taps publish.**

---

## 3a. News-Niche Compliance (this niche is special — non-negotiable)

The niche is **daily impact news/info explainers**. News on a faceless auto-channel carries
risks the generic playbook ignores. These rules are baked into the modules; full detail in
[08-news-niche-playbook.md](08-news-niche-playbook.md).

1. **Originality = the monetization gate.** YouTube's 2026 *Inauthentic Content* policy
   (2026-07-15) demonetized thousands of faceless AI channels that merely repackage reporting.
   **Every reel must add original analysis** ("why it matters / what it means for you"),
   not a summary. The facts are not the product — the analysis is. The daily human approval
   of 4–5 ideas is itself a "meaningful creative decision" the policy rewards.
2. **AI disclosure.** Set YouTube's altered/synthetic-content flag + a description disclosure
   line. (Auto-detected via SynthID/C2PA; India requires labeling within 3h of notice.) Our
   exposure is low — illustrative stock B-roll + synthetic voice, not fake footage of real
   people — but we disclose anyway.
3. **Copyright.** Never use broadcaster/agency footage; rewrite facts in own words + cite;
   narration is the primary asset, stock/CC0 B-roll + maps/charts secondary; cut every 5–8s.
4. **Accuracy & sensitivity.** Two-source minimum; neutral factual framing; soft/positive-impact
   lean; ideation auto-excludes communal/partisan/unverified-election/graphic topics.

---

## 4. Architecture

**Approach chosen: "Serverless Batch" + Claude-driven ideation.** The deterministic
production pipeline is one Python repository run by scheduled **GitHub Actions**. The daily
**ideation** step runs **Claude Code via an Anthropic Routine** (your Pro sub, in Anthropic's
cloud). **Supabase** holds state; **Telegram** is the approval interface. No server to
maintain, $0 beyond Pro, and the daily traffic keeps the Supabase project from auto-pausing.

```
        ┌────────────────────────────────────────────┐
 Daily  │  Anthropic Routine: Claude Code (Pro)       │
 08:00  │  → web-research trends → 15–20 scored ideas │
        │  → write rows to Supabase                   │
        │  (fallback: Gemini/Groq if cap/token issue) │
        └───────────────────────┬─────────────────────┘
                                 │ ideas → Supabase
                                 ▼
                  ┌─────────────────────────┐
                  │  Telegram Morning Digest │  ← ONLY human step
                  │  [Approve] / [Reject]    │
                  └────────────┬─────────────┘
                               │ 4–5 approved → Supabase queue
                               ▼
                 ┌───────────────────────────────────────┐
  Cron (GitHub   │  Production Pipeline (GitHub Actions): │
  Actions,       │  script→voice→visuals→assemble→        │
  staggered,     │  SUBTITLES→publish                     │
  UTC)           └───────────────────┬───────────────────┘
                                     │ post IDs → Supabase
                                     ▼
                 ┌───────────────────────────────────────┐
  Cron next day  │  Analytics + Learning (GitHub Actions) │
                 │  pull metrics → score hooks           │
                 └───────────────────┬───────────────────┘
                                     │ scores feed tomorrow's ideation
                                     └────────────────────────────────┘
```

### Why this split
- **Claude (Pro) does the high-value creative step** (trend research + ideation) where model
  quality matters most — sanctioned via official Claude Code / Routines.
- **Free deterministic tools do the mechanical steps** (script, voice, visuals, assembly,
  captions, publish) where reliability and $0 matter most.
- **vs. Always-on VM (Oracle + n8n):** more power but Linux maintenance + Oracle may reclaim
  idle instances (and Indian-card signup friction). Deferred to Phase 5.
- **vs. Local-first (PC + Task Scheduler):** only runs when the PC is on — violates the
  "reliable daily" goal. Rejected for MVP.

---

## 5. Modules (isolated, independently testable)

Each module is a Python package (or, for ideation, a Claude Routine) with one purpose and an
explicit input → output contract.

| # | Module | Input → Output | Engine / tool(s) | Phase |
|---|--------|----------------|------------------|-------|
| 1 | **Trend + Ideation** | (trend research) → 15–20 scored ideas (title, hook, angle, score) | **Claude Code (Pro) via Routine**; Gemini/Groq fallback | 1 |
| 2 | **Approval** | ideas → 4–5 approved | Telegram Bot API (inline buttons) | 1 |
| 3 | **Scriptwriter** | idea + template → script + caption + hashtags | Gemini/Groq (Claude optional); Templates A–D | 1 |
| 4 | **Voice** | script → narration `.wav` | edge-tts (default), Kokoro (fallback) | 1 |
| 5 | **Visuals** | keywords → B-roll clips | Pexels + Pixabay APIs | 1 |
| 6 | **Assembly** | audio + clips → 1080×1920 reel | FFmpeg (Ken Burns) | 1 |
| 7 | **Subtitles** | reel + audio → word-by-word burned captions | faster-whisper (WhisperX upgrade) + FFmpeg | **1** |
| 8 | **Thumbnail** | reel frame → cover image | Pillow / FFmpeg | 2 |
| 9 | **Publish** | reel + metadata → live / draft | YouTube Data API (auto); IG/TikTok later | 1 (YT), 3 (IG/TT) |
| 10 | **Analytics + Learning** | post IDs → metrics → hook/template scores | YouTube Analytics API → Supabase | 4 |

### Module contract principle
For each module a reader must answer *what it does, how to call it, what it depends on* —
without reading internals. Modules communicate only through typed data (Supabase rows or
function returns), never shared globals.

---

## 6. Data Model (Supabase Postgres)

| Table | Key columns | Purpose |
|-------|-------------|---------|
| `ideas` | id, date, niche, title, hook, angle, est_score, **sources** (URLs), status (`pending`/`approved`/`rejected`) | Daily ideation output + sources + approval state |
| `scripts` | id, idea_id (FK), template, body, caption, hashtags | Generated scripts |
| `posts` | id, script_id (FK), platform, external_id, url, status, published_at | Published/queued outputs per platform |
| `analytics` | id, post_id (FK), pulled_at, views, retention, likes, comments, shares, saves | Time-series metrics |
| `hook_performance` | id, hook_text, niche, uses, avg_retention, avg_views | Aggregated learning signal |

**Asset policy:** Render locally → upload to platform → **delete local file**. Never store
video in Supabase (1 GB cap). Daily cron writes keep the free project from auto-pausing.

---

## 7. Content System (no fully-random generation)

**Templates (reused, not improvised):**
- **A** — Hook → Problem → Solution → Twist → CTA
- **B** — Controversial statement → Explanation → Examples → Conclusion
- **C** — Story → Curiosity loop → Escalation → Reveal
- **D** — Fast listicle → Rapid pacing → Short captions → Quick dopamine *(MVP default)*

**Niche:** `impact-news` — Claude researches the day's high-impact developments (India +
world, soft/positive lean), prefers under-covered angles (originality), and captures source
URLs per idea. **Template N (News Impact Explainer)** is the default. **Hook database:** seed
library tuned for impact-news; store per-hook retention/views/niche; ideation remixes top
performers (Module 10 → Module 1 loop). See [08-news-niche-playbook.md](08-news-niche-playbook.md).

**Retention hacks (phased in P2+):** Agent Debate (two TTS voices), beat-sync cutting,
1-frame Easter-egg + "comment the timestamp" CTA, programmatic code/terminal B-roll,
3-hook A/B variants, auto-pinned seed comment on publish.

---

## 8. Development Roadmap

- **Phase 1 — MVP.** Modules 1→2→3→4→5→6→**7 (subtitles)**→9(YouTube only), Template D,
  Claude-driven ideation via Routine. **Exit: 4–5 captioned YouTube Shorts/day, reliable,
  one human tap, 7 days running.**
- **Phase 2 — Quality.** Kokoro + debate voices, thumbnails, beat-sync, WhisperX upgrade,
  programmatic B-roll.
- **Phase 3 — Multi-platform.** Instagram Reels (after Meta App Review) + TikTok drafts.
- **Phase 4 — Learning loop.** Analytics ingestion + hook/template scoring feeding ideation.
- **Phase 5 — Multi-niche scale.** Oracle Free ARM VM + n8n; one infra, multiple brands.

---

## 9. Cost & Risk

**Cost:** **$0/month** beyond your existing Claude Pro subscription. No new paid services at
4–5 reels/day.

**Risks & mitigations:**
| Risk | Mitigation |
|------|------------|
| Routines is research preview (limits/API may change) | Opt-in Gemini/Groq fallback keeps the digest alive if Routines behaves differently |
| Routines daily run caps / Claude Pro usage limits | Daily ideation is light (~1 session); fallback fires if a cap is hit |
| `CLAUDE_CODE_OAUTH_TOKEN` expires (~1 yr) | Calendar reminder to re-run `claude setup-token`; fallback covers the gap |
| ToS: no OAuth token in custom scripts/Agent SDK | Ideation runs **only** via official Claude Code / Routines, individual scale |
| `claude-code-action` cron auth bug | Use Anthropic **Routines** for scheduling (not GH `schedule:` for Claude) |
| edge-tts breaks (unofficial) | Kokoro TTS fallback |
| Instagram needs Meta App Review (days–weeks) | Start review early; YouTube carries MVP |
| TikTok Direct Post needs audit (2–6 wks) | Semi-auto draft until audited |
| GitHub Actions is UTC-only | Schedule with UTC offset for 08:00 local digest |
| Supabase free project auto-pauses (7 idle days) | Daily cron writes keep it warm |
| Oracle signup friction (Indian cards) | Don't depend on Oracle for MVP; GitHub Actions carries it |
| YouTube quota ceiling | ~100 uploads/day ≫ need; monitor `videos.insert` usage |

---

## 10. Critical Rules (non-negotiable)

1. Do **not** chase perfection early.
2. Hooks matter more than visuals.
3. Retention matters more than followers.
4. Consistency beats cinematic quality.
5. Use templates — do not generate everything randomly.
6. Analyze performance continuously.
7. Keep the human approval layer (the Morning Digest). AI still produces occasional cringe.

---

## 11. Out of Scope (MVP)

- Reliable generative text-to-video at daily volume.
- Instagram/TikTok full automation before platform approvals land.
- Multi-niche orchestration (Phase 5).
- Local GPU rendering as the primary path.
- Piping a Claude Pro OAuth token into custom code (ToS violation — never).

---

## Appendix A — Source References (2026)

- YouTube quota reduction & upload API:
  https://www.getphyllo.com/post/is-the-youtube-api-free-costs-limits-iv ·
  https://postproxy.dev/blog/youtube-upload-api-guide/
- Claude Code setup-token / OAuth for automation:
  https://github.com/anthropics/claude-code-action/blob/main/docs/setup.md
- Claude Routines (cloud-scheduled Claude Code):
  https://code.claude.com/docs/en/routines ·
  https://9to5mac.com/2026/04/14/anthropic-adds-repeatable-routines-feature-to-claude-code-heres-how-it-works/
- Claude Pro / Claude Code usage limits:
  https://www.truefoundry.com/blog/claude-code-limits-explained
- Claude consumer ToS / automation rules:
  https://privacy.claude.com/en/articles/9301722-updates-to-our-acceptable-use-policy-now-usage-policy-consumer-terms-of-service-and-privacy-policy ·
  https://www.theregister.com/2026/02/20/anthropic_clarifies_ban_third_party_claude_access/
- Gemini free tier: https://tokenmix.ai/blog/gemini-api-free-tier-limits
- Groq free tier: https://tokenmix.ai/blog/groq-free-tier-limits-2026
- Kokoro / open TTS: https://www.bentoml.com/blog/exploring-the-world-of-open-source-text-to-speech-models
- faster-whisper: https://localaimaster.com/blog/faster-whisper-guide
- Stock B-roll: https://posteverywhere.ai/blog/8-best-websites-for-free-stock-videos-for-social-media
- Instagram Graph API publishing: https://developers.facebook.com/docs/instagram-platform/content-publishing/
- TikTok Content Posting API: https://developers.tiktok.com/products/content-posting-api/
- GitHub Actions cron: https://davidmuraya.com/blog/schedule-python-scripts-github-actions/
- Oracle Cloud Free Tier: https://www.oracle.com/cloud/free/
- Supabase free tier: https://supabase.com/pricing
- OSS references: https://github.com/RayVentura/ShortGPT ·
  https://github.com/SamurAIGPT/AI-Youtube-Shorts-Generator ·
  https://github.com/SaarD00/AI-Youtube-Shorts-Generator
