# AI Reel Factory — Design Specification

> **Design record** (written at the start of the project). Current state: [STATUS.md](../STATUS.md);
> operating rules: [CLAUDE.md](../CLAUDE.md); as-built diagram: [07-architecture-diagram.md](07-architecture-diagram.md).
> Where the build changed a decision, the original is struck through or followed by an
> *As built* note (checked against the code on 2026-10-09).

**Date:** 2026-05-31
**Status:** Approved (design phase)
**Owner:** Shaan Satsangi
**Channel:** But It Matters (daily impact news/info explainers, India + world)

---

## 1. Vision & Primary Goal

Build a **near-zero-cost autonomous AI content system** that generates ideas, writes
scripts, narrates, assembles vertical video, captions, and publishes — requiring exactly
**one human action per day**: approving 4–5 of ~15–20 generated ideas via a Telegram
"Morning Digest."

> **Primary goal (in priority order):** Reliably produce and publish **4–5 automated
> reels per day**. Consistency beats sophistication. Do not chase perfection early.

The operator acts as the *creative director* of an autonomous media machine.

*As built:* there is no morning schedule. The operator starts each run on demand (`/makeshort`
in the Telegram bot, or the `make-short` workflow's Run button) and approves from that run's
digest. A digest offers a few ideas (3 from the Run button, 5 from a bare `/makeshort`, topped
up around any still pending) and a run takes at most 3 approvals (`APPROVAL_CAP`). The 4–5/day
goal is unchanged.

---

## 2. Decisions That Anchor This Design

These were confirmed with the operator and drive every downstream choice:

| Decision | Choice | Consequence |
|----------|--------|-------------|
| Operator skill | **Can code (Python)** | Custom Python pipeline, no no-code lock-in |
| Publishing posture | **Official APIs + semi-auto** | Auto where sanctioned; manual tap where ToS-risky |
| First platform | **YouTube Shorts** | Only platform with free, ToS-safe full automation |
| Runtime | **Cloud / always-on** | GitHub Actions; PC-independent reliability. *As built:* runs start on demand; the scheduled digests were removed on 2026-09-29 (GitHub started them 6.5–7 h late) |
| **Ideation engine** | ~~Claude Code (Pro) via Anthropic Routines~~ → **Gemini on Vertex AI** (grounded search), Groq for story selection and failover | *As built:* the Routine never ran in production; `routines/ideation.md` is optional and dormant. Ideation runs in `src/ideation_fallback.py` on every run |
| **Ideation runner** | ~~Anthropic Routines (cloud)~~ → **each on-demand `make-short` run** | Ideas are generated at the start of the run, just before its digest |
| **Subtitles** | **In MVP (Phase 1)** | Word-by-word captions from day one (retention driver) |
| **Niche** | **Daily impact news/info explainers** (India + world), ~~soft/positive lean~~ → **truth-first** (2026-07-27) | Ideation researches the day's high-impact developments; explainer format; verdicts allowed where the evidence supports them; triggers news-specific compliance rules — see §3a + [08-news-niche-playbook.md](08-news-niche-playbook.md) |
| **Content style** | **Daily impact explainer** (what happened → why it matters → impact) | Batches into the approval digest; maximizes monetization-safe originality |

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
   *As built (findings 2–4):* no Routine has run in production, so none of this is exercised.
   The ToS boundary in finding 2 still holds (CLAUDE.md rule 4).
5. **Free LLMs as the fallback safety-net.** ~~Gemini free: 1,500 req/day, 1M tokens/min.
   Groq free: 14,400 req/day on Llama 3.1‑8B, 1,000/day on Llama 3.3‑70B, per-model limits.
   Fires only if a Routine cap is hit or the token lapses, so the digest never fails.~~
   *As built:* Gemini is the **primary** engine for ideation, scripts and the fact check, served
   through **Vertex AI**: billed per token, with Gemini 3 grounded search free for 5,000 queries
   a month and billed after that. The Developer API's free grounded search came to 20 requests a
   day, shared by ideation, the scriptwriter and the fact check (measured 2026-09), which is why
   production moved to Vertex. Groq `openai/gpt-oss-120b` (free) selects the stories and is the
   failover for ungrounded calls; Groq has no grounded search.
6. **TTS resilience.** The engine is an ordered **fallback chain**, so a reel never goes without
   a voice; Kokoro (Apache‑2.0, CPU, offline-safe) is the last-resort floor. An earlier revision
   of this spec put Google Chirp 3 HD first (`Chirp 3 HD → edge-tts (en-IN) → Kokoro`).
   *As built:* the channel voice is **Gemini TTS** `gemini-3.1-flash-tts-preview`, voice
   **Zubenelgenubi** (chosen by ear), and every link keeps one male narrator: Gemini Developer
   API → the same model on Vertex AI (billed) → Developer `gemini-2.5-flash-preview-tts` → Vertex
   `gemini-2.5-flash-tts` → Chirp 3 HD `en-IN-Chirp3-HD-Zubenelgenubi` → edge-tts
   `en-IN-PrabhatNeural` → Kokoro `am_michael`. The Developer API shuts down both of its TTS
   models on 2026-11-17; the successor voice is to be picked by ear first (see STATUS.md).
7. **Subtitles (now MVP).** **faster-whisper** (CPU-friendly, word timestamps) is the
   default for karaoke word-by-word captions; **WhisperX** is the higher-accuracy upgrade.
8. **AI images, not generative video, at daily volume.** Free Veo/Runway *video* tiers are
   rate-capped and unreliable. The pipeline generates **AI B-roll images** (Cloudflare Workers AI
   FLUX.2 klein, then FLUX.1 schnell; free tier) + Ken Burns motion as the primary source
   (`VISUAL_SOURCE=ai`), falling back to **Pexels/Pixabay stock**. The stock licences are free
   but **not CC0**: no identifiable person may appear in a bad light, so the queries keep faces
   out of frame. Generative *video* remains a later garnish.
9. **Hosting.** **GitHub Actions** is the best free runner for the deterministic Python
   pipeline (unlimited minutes on public repos; ~2,000/mo private; runs in **UTC**).
   ~~Anthropic **Routines** handles the Claude ideation step (sidesteps the known
   `claude-code-action` cron auth bug).~~ Oracle Always-Free ARM VM is reserved for Phase 5
   (note: Indian debit cards often fail Oracle signup — don't depend on it for MVP).
   *As built:* production runs on demand (`workflow_dispatch`), because GitHub started scheduled
   runs hours late; only the tests and the daily analytics job keep a schedule. A small stdlib
   webhook bot on **Vercel** (Hobby plan) is the Telegram control surface. No Routine runs.
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
   not a summary. The facts are not the product — the analysis is. The human approval of
   every idea is itself a "meaningful creative decision" the policy rewards.
2. **AI disclosure.** Set YouTube's altered/synthetic-content flag + a description disclosure
   line. (Auto-detected via SynthID/C2PA; India requires labeling within 3h of notice.) Our
   exposure is low — illustrative AI images or stock B-roll, a synthetic voice and AI-generated
   music, never fake footage of real people — but we disclose anyway. As built, with AI visuals
   (the live setting), the line reads "AI-generated narration, images and music."
3. **Copyright.** Never use broadcaster/agency footage; rewrite facts in own words + cite;
   narration is the primary asset; our own AI illustrations or Pexels/Pixabay stock (free
   licences, not CC0) + maps/charts are secondary; cut every 5–8s.
4. **Accuracy & sensitivity.** Two-source minimum (`MIN_SOURCES`). ~~Neutral factual framing;
   soft/positive-impact lean.~~ **Truth over neutrality** (operator policy, 2026-07-27): the
   channel may reach a verdict and name who is responsible, and the sharper the verdict, the
   more certain its facts must be. `src/factcheck.py` re-checks every finished script before it
   is voiced and blocks fabrication. Politics is in scope; the sensitivity filter still applies
   (communal/religious incitement, anything that could inflame violence, rumour stated as fact,
   deepfakes, graphic tragedy exploitation, medical or financial advice stated as fact). The
   models are asked to apply it and the approval tap backstops it; in code, only stories about
   deaths or serious harm are flagged (a somber tone, and "Sensitive" in the digest). See
   [08-news-niche-playbook.md](08-news-niche-playbook.md) §5.

---

## 4. Architecture

**Approach chosen: "Serverless Batch" + Claude-driven ideation.** The deterministic
production pipeline is one Python repository run by scheduled **GitHub Actions**. The daily
**ideation** step runs **Claude Code via an Anthropic Routine** (your Pro sub, in Anthropic's
cloud). **Supabase** holds state; **Telegram** is the approval interface. No server to
maintain, $0 beyond Pro, and the daily traffic keeps the Supabase project from auto-pausing.

> *As built (2026-10):* still serverless batch, but **on demand**: a run starts from
> `/makeshort` in the Telegram bot or the `make-short` workflow's Run button, and nothing is
> scheduled except the tests and the daily analytics job. **Ideation runs inside that run** on
> Gemini (Vertex AI) and Groq, not in a Claude Routine. A small webhook bot on **Vercel** records
> the approval taps in Supabase and starts runs. Every script passes a **fact-check gate** before
> it is voiced. Cost is ≤ $5/month beyond Pro, with Vertex AI and Cloud Text-to-Speech billed
> (§9). The analytics job's daily writes keep Supabase awake. The as-built diagram is in
> [07-architecture-diagram.md](07-architecture-diagram.md).

The original design (2026-05-31):

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
- *As built:* no Routine runs, so Gemini on Vertex AI (Groq as failover) does the creative steps
  too: ideation, the script and the fact check. That usage is billed, inside the ≤ $5/month cap.
- **vs. Always-on VM (Oracle + n8n):** more power but Linux maintenance + Oracle may reclaim
  idle instances (and Indian-card signup friction). Deferred to Phase 5.
- **vs. Local-first (PC + Task Scheduler):** only runs when the PC is on — violates the
  "reliable daily" goal. Rejected for MVP.

---

## 5. Modules (isolated, independently testable)

Each module is a Python module in `src/` with one purpose and an explicit input → output
contract. (Ideation was designed as a Claude Routine; as built it is `src/ideation_fallback.py`.)

| # | Module | Input → Output | Engine / tool(s) | Phase |
|---|--------|----------------|------------------|-------|
| 1 | **Trend + Ideation** | news + trends → scored, sourced ideas (title, hook, angle, score, ≥ 2 sources) | ~~Claude Code (Pro) via Routine~~ *As built:* Google News + Trends RSS → Groq picks the stories → **Gemini on Vertex AI** researches them with grounded search; Groq failover | 1 |
| 2 | **Approval** | ideas → approved (at most 3 per run, `APPROVAL_CAP`) | Telegram Bot API (inline buttons: Approve / Reject / Pass); taps recorded by the webhook bot on Vercel | 1 |
| 3 | **Scriptwriter** | idea + template → script + caption + hashtags | Gemini on Vertex AI (grounded write), Groq failover; **Template N** (25–30s, hook-judge punch-up, 80-word cap) | 1 |
| 4 | **Voice** | script → narration `.wav` | **Gemini TTS, voice Zubenelgenubi (Developer API → Vertex AI) → Chirp 3 HD → edge-tts (en-IN) → Kokoro** (fallback chain, one male narrator) | 1 |
| 5 | **Visuals** | keywords → B-roll clips | **AI: Cloudflare Workers AI FLUX + Ken Burns** → Pexels photos → Pexels/Pixabay stock video | 1 |
| 6 | **Assembly** | audio + clips → 1080×1920 reel | FFmpeg — **xfade · cinematic grade · vignette/grain · music ducking · brand-logo bug · loop** (toggle-gated, fail-soft) | 1 |
| 7 | **Subtitles** | reel + audio → burned captions | faster-whisper — **karaoke + frame-1 hook + key-point cards + source lower-third** + FFmpeg | **1** |
| 8 | **Thumbnail** | reel frame → cover image | Pillow / FFmpeg | 2 |
| 9 | **Publish** | reel + metadata → live / draft | YouTube Data API (auto); IG/TikTok later | 1 (YT), 3 (IG/TT) |
| 10 | **Analytics + Learning** | post IDs → metrics → hook/template scores | YouTube Analytics API → Supabase. *As built (basic):* a daily job snapshots views, likes and comments through the YouTube **Data** API, and recent winners and low performers feed the ideation prompt; hook/template scoring is not built | 1 (basic), 4 |
| 11 | **Fact check** *(added in the build; runs after 3, before 4)* | finished script + sources → pass / block | Gemini on Vertex AI with grounded search, 2 samples; blocks fabrication, waives imprecision; one repair pass, then a re-check | 1 |

### Module contract principle
For each module a reader must answer *what it does, how to call it, what it depends on* —
without reading internals. Modules communicate only through typed data (Supabase rows or
function returns), never shared globals.

---

## 6. Data Model (Supabase Postgres)

| Table | Key columns | Purpose |
|-------|-------------|---------|
| `ideas` | id, created_at, niche, title, hook, angle, est_score, **sources** (URLs), status (`pending` / `approved` / `rejected` / `passed` / `produced` / `blocked`) | Ideation output + sources + approval state (`passed` = untapped or skipped; `blocked` = stopped by the fact check) |
| `scripts` | id, idea_id (FK), template, body, caption, hashtags, title, factcheck (jsonb verdict) | Generated scripts + the published title + the gate's verdict |
| `posts` | id, script_id (FK), platform, external_id, url, status (`published` / `removed`), published_at, voice | Published outputs per platform; `voice` records the engine and model that spoke |
| `analytics` | id, post_id (FK), pulled_at, views, retention, likes, comments, shares, saves | Time-series metrics; the daily job fills views, likes and comments only (the Data API has no retention) |
| `hook_performance` | id, hook_text, niche, uses, avg_retention, avg_views | Planned learning signal; the table exists but nothing reads or writes it (Phase 4) |

**Asset policy:** Render locally → upload to platform → **delete local file**. Never store
video in Supabase (1 GB cap). The daily analytics job's writes keep the free project from
auto-pausing.

---

## 7. Content System (no fully-random generation)

**Templates (reused, not improvised):**
- **A** — Hook → Problem → Solution → Twist → CTA
- **B** — Controversial statement → Explanation → Examples → Conclusion
- **C** — Story → Curiosity loop → Escalation → Reveal
- **D** — Fast listicle → Rapid pacing → Short captions → Quick dopamine

**Niche:** `impact-news` — ideation researches the day's high-impact developments (India +
world, truth-first: see §3a.4), prefers under-covered angles (originality), and captures source
URLs per idea. **Template N (News Impact Explainer)** is the default and, as built, the only
template wired (`src/scriptwriter.py` embeds it; A–D remain reference designs). **Hook
database:** seed library tuned for impact-news (in [05-content-system.md](05-content-system.md)).
The planned per-hook scoring (Module 10 → Module 1 loop) is not built; as built, the ideation
prompt gets recent winning and low-performing titles by views instead. See
[08-news-niche-playbook.md](08-news-niche-playbook.md).

**Retention hacks (phased in P2+):** Agent Debate (two TTS voices), beat-sync cutting,
1-frame Easter-egg + "comment the timestamp" CTA, programmatic code/terminal B-roll,
3-hook A/B variants, auto-pinned seed comment on publish.

---

## 8. Development Roadmap

- **Phase 1 — MVP.** ✅ **Built & publishing live** (versions: [CHANGELOG.md](../CHANGELOG.md)).
  Modules 1→2→3→**11 (fact check)**→4→5→6→**7 (subtitles)**→9 (YouTube only), Template N,
  ~~Claude-driven ideation via Routine~~ ideation on Gemini (Vertex AI). Shipped *beyond* the
  original MVP scope: the **fact-check gate**, the **Gemini TTS** channel voice with a same-voice
  fallback chain, **AI B-roll** (Cloudflare FLUX + Ken Burns), **premium auto-editing**
  (transitions, grade, music bed, ducking, brand bug, loop), the **Telegram control bot** on
  Vercel, and a basic analytics loop. **Exit: 4–5 captioned Shorts/day, reliable, one human tap,
  7 days running** — not met yet; the system runs on demand with at most 3 approvals per run
  (see STATUS.md).
- **Phase 2 — Quality.** Debate voices, thumbnails, beat-sync, WhisperX upgrade, AI-image
  fidelity (paid-ready Imagen), audio polish.
- **Phase 3 — Multi-platform.** Instagram Reels (after Meta App Review) + TikTok drafts.
- **Phase 4 — Learning loop.** Analytics ingestion + hook/template scoring feeding ideation.
  (A basic version runs already: daily view snapshots, with recent winners fed to ideation.)
- **Phase 5 — Multi-niche scale.** Oracle Free ARM VM + n8n; one infra, multiple brands.

---

## 9. Cost & Risk

**Cost:** **≤ $5/month** beyond your existing Claude Pro subscription (raised from $0 on 2026-06-15
to fund near-human voice). ~~Google Cloud TTS is free at our 4–5 reels/day volume, so the $5 is headroom.~~
*As built:* the billed services are both in the Google Cloud project `but-it-matters-tts`:
**Vertex AI** (Gemini text, grounded search, the fact check and the same-voice TTS fallback;
tokens are billed on every call, and Gemini 3 grounded search is free for 5,000 queries a month,
then billed) and **Cloud Text-to-Speech** (Chirp, now a late fallback). The Lyria music beds were
a one-off $0.66. A ₹450/month budget with 50/90/100% alerts guards the billing account; it alerts
but does not stop spending. Everything else runs on free tiers.

**Risks & mitigations:**
| Risk | Mitigation |
|------|------------|
| Claude Routine risks: research preview, daily run caps and shared Pro usage, `CLAUDE_CODE_OAUTH_TOKEN` expiry (~1 yr), the `claude-code-action` cron auth bug | Moot as built: no Routine runs; ideation is Gemini (Vertex AI) with Groq failover. They apply again only if the optional Routine is switched on |
| ToS: no OAuth token in custom scripts/Agent SDK | Claude is used **only** via official Claude Code / Routines, individual scale; the pipeline's code never calls Claude |
| edge-tts breaks (unofficial) | Kokoro TTS fallback |
| Gemini models retire (previews and point releases have short lifetimes) | Each model is a setting, and the grounded ones are ordered chains (a retired model moves the call down the chain); the TTS chain falls through the same voice on Vertex. The Developer-API TTS models shut down 2026-11-17 (see STATUS.md) |
| Instagram needs Meta App Review (days–weeks) | Start review early; YouTube carries MVP |
| TikTok Direct Post needs audit (2–6 wks) | Semi-auto draft until audited |
| ~~GitHub Actions is UTC-only~~ GitHub starts scheduled runs hours late | Production runs on demand only; the scheduled tests and analytics jobs don't depend on the hour |
| Supabase free project auto-pauses (7 idle days) | The daily analytics job's writes keep it warm |
| Oracle signup friction (Indian cards) | Don't depend on Oracle for MVP; GitHub Actions carries it |
| YouTube quota ceiling | ~100 uploads/day ≫ need; monitor `videos.insert` usage |
| Vertex AI spend creeps up | Budget alerts on the billing account; Developer API first for TTS (free tier) |

---

## 10. Critical Rules (non-negotiable)

1. Do **not** chase perfection early.
2. Hooks matter more than visuals.
3. Retention matters more than followers.
4. Consistency beats cinematic quality.
5. Use templates — do not generate everything randomly.
6. Analyze performance continuously.
7. Keep the human approval layer (the Telegram digest). AI still produces occasional cringe.

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
