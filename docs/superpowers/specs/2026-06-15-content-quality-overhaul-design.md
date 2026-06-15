# Design Spec — Content-Quality Overhaul ("make the Shorts actually good")

**Date:** 2026-06-15
**Status:** Draft for operator review
**Owner decisions captured:** voice → Google Cloud **Chirp 3 HD**; budget → **≤ $5/month** total
(raised from $0, CLAUDE.md synced); effort → **1-tap default + optional light human touch**;
format → **recommend-what-wins** (decided below: stay faceless, go *visual-first*).

> This spec is grounded in the live pipeline (every claim below cites the actual module) and in
> 2026 web research (sources at the end). It does **not** add code yet — it is the design to
> approve before we write the implementation plan.

---

## 1. Problem & goal

The pipeline ships reliably (v0.2.1, 153 tests) but output quality is weak across **content,
voice, visuals, captions, and metadata**. Goal: raise per-Short quality to "watchable and
honest" without breaking the near-one-tap-a-day model or the ≤$5/month budget, **and** de-risk
the channel against YouTube's 2026 automation crackdown.

### Two root causes (the strategic reframe — fix these or the rest is cosmetic)

1. **"MAX HYPE" tuning fights the 2026 algorithm.** The scriptwriter/ideation prompts chase
   clickbait/conflict framing ([scriptwriter.py:48-51](../../../src/scriptwriter.py#L48-L51),
   [ideation_fallback.py:44-52](../../../src/ideation_fallback.py#L44-L52)). YouTube now analyzes
   actual audio/visual/speech vs. packaging and suppresses click→swipe mismatch; "one dishonest
   thumb can drag your next five uploads down." Hype is likely the #1 content problem.
2. **Full automation = "AI-slop" monetization risk.** Jan-2026 **Inauthentic Content Policy**
   evaluates *whole channels* on a 3-strike system; it demonetizes mass-produced, no-human-input,
   generic-stock content. The safe harbor is **human editorial perspective**. Our generic
   explainer + generic stock + robotic American TTS + clickbait title is the textbook slop
   profile. Every fix below also moves us off that profile.

**Format verdict (the "recommend what wins" answer): stay faceless, go visual-first; do NOT add
an AI avatar.** Avatars show ~+25% RPM but *reduce* retention for curiosity/B-roll/explainer
styles (ours), and add setup + platform risk. Winner for our constraints = visual-first explainer
+ real human angle + great voice + karaoke captions.

---

## 2. Scope

**In scope (5 work areas):** voice engine, content/script + topic sourcing, visuals, captions,
metadata — plus an optional light-touch operator lever and doc sync.

**Out of scope (YAGNI / rule 9):** AI avatar/presenter; paid AI video gen (Kling etc.);
ElevenLabs (its credit model can't cover ~150 videos/mo cheaply); long-form; multi-platform.

**Hard constraints (unchanged):** headless on GitHub Actions (UTC); fallback chains mandatory
(rule 11); idempotent + fail-soft (rules 12/14); accuracy is the hard line; AI disclosure stays;
≤ $5/month with a hard cap; no Claude dev-API (rule 4).

---

## 3. Per-area design

### 3.1 Voice → Google Cloud Chirp 3 HD (primary), with a stronger fallback chain  ★ biggest perceived win
- **Current:** `voice.py` defaults to Kokoro int8 `af_heart` — an *American, quantized* voice
  ([voice.py:103](../../../src/voice.py#L103)) → robotic, wrong accent for an India channel.
- **Target:** new engine `VOICE_ENGINE=google` using **Google Cloud TTS Chirp 3 HD**, an
  **en-IN** Chirp 3 HD voice. Free within **1M chars/mo**; our ~117k chars/mo (≈5/day) stays
  free, so the $5 budget is pure headroom (overage is $30/1M → $5 ≈ 167k extra chars).
- **New fallback chain (rule 11):** Google Chirp 3 HD → **edge-tts `en-IN-NeerjaNeural`**
  (free, no key, neural-quality, already in repo) → Kokoro. (Reorders today's Kokoro→edge.)
- **Implementation notes:**
  - Add a `_synthesize_google()` path. Fetch current SDK/REST usage via **Context7**
    (`google-cloud-texttospeech`) before coding (rule 17) — do not hand-write from memory.
  - **Pick the exact en-IN Chirp 3 HD voice from the live `voices.list` API** (Chirp 3 HD voice
    IDs change); don't hard-code an unverified name. Expose via `GOOGLE_TTS_VOICE` /
    `GOOGLE_TTS_LANGUAGE` (default `en-IN`).
  - **Headless auth:** restricted **API key** (TTS API only) in a GitHub secret
    (`GOOGLE_TTS_API_KEY`) is simplest for Actions; service-account JSON is the alternative.
  - Keep `synthesize()`'s contract `(audio_path, duration_s)` and deterministic filenames
    (rule 12). Dramatic-pacing logic stays for the Kokoro path; for Google, prefer SSML/marks
    or a light inter-sentence join.
- **Operator step (one-time):** create a Google Cloud project, enable Cloud TTS, create the
  restricted API key, **set a hard $5 budget cap + alert** so it can never overrun.
- **Config knobs:** `VOICE_ENGINE`, `GOOGLE_TTS_API_KEY`, `GOOGLE_TTS_VOICE`,
  `GOOGLE_TTS_LANGUAGE`.

### 3.2 Content & script — kill the hype, add the human "why it matters"  ★ root-cause fix
- **Current:** `_PROMPT_N` and ideation prompt optimize for drama/over-promise; `_PUNCHUP_PROMPT`
  intensifies hooks. Accuracy guard already strong (keep it).
- **Target prompt changes (no code architecture change — prompt + light glue):**
  - Replace "MAX HYPE / over-promise drama" with **honest curiosity + promise↔payoff alignment**.
    The hook still stops the scroll, but the title must sit truthfully on what the video delivers.
  - Add a required **"why it matters" human-perspective beat** — a genuine analytical take/angle
    (the monetization safe-harbor against the slop policy).
  - Keep: accuracy hard-line, retention-loop ending, <15-word sentences, 0–3s hook, ~110–130 words.
  - Soften the punch-up judge from "rewrite below 9" to fix only genuinely weak/flat hooks; never
    introduce mismatch.
- **Topic sourcing upgrade:** `trends.py` uses raw Google-Trends-India RSS (random viral noise,
  [trends.py:23](../../../src/trends.py#L23)). Add **curated news RSS** (Google News RSS by
  topic/region — free, no key) so ideation works from real impact-news headlines, not just
  trending search terms. Best-effort (rule 11), merged into the ideation prompt context.
- **Config knobs:** `ENABLE_HUMAN_ANGLE`, `NEWS_RSS_FEEDS`, existing `HOOK_*`.

### 3.3 Visuals — story-specific, visual-first; kill the generic-stock slop look  ★ most code
- **Current:** proper nouns stripped → generic stock photos ("parliament building", "indian
  flag") + Ken Burns ([visuals.py:74-85](../../../src/visuals.py#L74-L85)). This *is* the
  underperforming slop pattern.
- **Target (news = text + data + specifics, not cinematic B-roll):**
  1. **Bold on-screen TEXT cards** at key beats (the core fact / number / name) — free via the
     FFmpeg/ASS layer; story-specific; high-retention. *Biggest single visual lever.*
  2. **Headline cards** (the real source's headline as styled text + on-screen citation) instead
     of scraping article screenshots — keeps copyright-safe (docs/08 §3) while being specific.
  3. **Stock/Ken-Burns becomes the *background***, not the whole message. Improve keyword
     specificity where copyright allows; keep CC0-only.
  4. *(Stretch)* simple **maps/charts** for impact stories (free generation), behind a toggle.
- **Implementation:** likely a new small `overlays.py` (text-card / headline-card ASS or drawtext
  builder) consumed by `assembly.py`/`subtitles.py`; AI image path (Cloudflare Flux) stays
  available but is **not** the primary answer (AI-image-only = slop risk).
- **Config knobs:** `ENABLE_TEXT_CARDS`, `ENABLE_HEADLINE_CARD`, `ENABLE_DATA_VIZ` (default off).

### 3.4 Captions — active-word karaoke + a real font  ★ easy retention lift
- **Current:** Arial 112px, 2 static words, no active-word highlight
  ([subtitles.py:137](../../../src/subtitles.py#L137)). We already have whisper word timings.
- **Target:** **active-word karaoke** — phrase in white, the *currently spoken* word highlighted
  (yellow/mint), in **Montserrat/Poppins Bold**. Research: word-highlighting outperforms static
  captions for faceless/explainer content.
- **Implementation:** change the ASS `[V4+ Styles]` + event builder to emit per-word highlight
  (ASS `\k`/karaoke or a Highlight style on the active word). **Bundle the font** in
  `assets/fonts/` and pass `fontsdir` to libass (CI has no Montserrat). Keep the frame-1 hook
  banner.
- **Config knobs:** `CAPTION_FONT`, `CAPTION_HIGHLIGHT_COLOR`, existing `CAPTION_WORDS`.

### 3.5 Metadata — minor tuning (smallest lever; Shorts rank on performance, not metadata)
- **Tags:** cap at **8–12** (currently 10–15), **first tag = main keyword** (highest weight)
  in `scriptwriter` / `production._build_metadata` / `publish._cap_tags`.
- **Description:** ensure the **primary keyword sits in the first ~125 chars** (preview window).
- **Hashtags:** keep **≤5 meaningful** (first 3 render above the title); brand footer already fine.

### 3.6 Optional light-touch lever (the "I'll tweak it" path you chose)
- Add an **optional operator "hot take" / edit** via Telegram that the scriptwriter weaves into
  the "why it matters" beat. **Default stays 1-tap** (auto-runs without it); when provided, it
  both lifts quality and strengthens the human-authorship/anti-slop signal.
- Mark as a discrete, independently-shippable sub-feature (can land last).

---

## 4. Sequencing (quick wins first)

- **Phase A — quick wins (high impact, low code):** 3.1 voice (Google Chirp 3 HD + fallback
  reorder) · 3.2a de-hype prompts + human-angle · 3.4 karaoke captions + font.
- **Phase B — visual-first + better topics:** 3.3 text/headline cards + keyword specificity ·
  3.2b curated news RSS sourcing.
- **Phase C — polish & lever:** 3.6 optional hot-take lever · 3.5 metadata trims · doc sync
  (remaining: docs/01, docs/07, docs/04 free-tools, CHANGELOG, STATUS) + version bump.

---

## 5. Cross-cutting requirements

- **Reliability (rule 11):** every new engine/source behind a fallback chain + a config toggle
  that fails soft (rule 14). A Google-TTS outage must drop to edge-tts, never kill the run.
- **Idempotency (rule 12):** preserve deterministic artifact names; reruns never double-spend.
- **Budget guardrail:** Google Cloud hard cap + alert; log monthly char usage (rule 13).
- **Compliance (docs/08 + 2026 policy):** keep CC0-only visuals, AI-disclosure flag + line, ≤10/day,
  accuracy hard-line; the human-angle beat is the anti-slop authorship signal.
- **Testing (rule 8):** unit tests per change (mock Google TTS client + fallback; ASS karaoke
  build; text-card filter argv; metadata caps), live-gated tests for real Google synth + render.
  Keep the suite green (currently 153).

## 6. Risks & open questions

- **Chirp 3 HD voice IDs / REST shape** — verify live via voices.list + Context7 before coding
  (don't trust memory). *Open:* exact en-IN Chirp 3 HD voice to pick (operator may have a
  preference once we list samples).
- **edge-tts reliability in CI** — it uses an undocumented MS endpoint; acceptable as *fallback*,
  not primary (hence Google primary).
- **Font licensing** — use an OFL font (Montserrat/Poppins) so bundling is license-clean.
- **Text-card density** — too much on-screen text harms retention; tune beats, keep it sparse.

## 7. Definition of done

Each phase: code + tests green + config knobs wired into both workflows + STATUS/CHANGELOG
updated. Overall: a generated Short has a natural en-IN voice, an honest aligned title, ≥1
story-specific text/headline card, active-word karaoke captions, and trimmed metadata — and the
default run still needs only one tap.

---

## Sources (2026 research)

- Algorithm / hooks / retention: [Virvid](https://virvid.ai/blog/faceless-youtube-algorithm-retention-2026) ·
  [Conbersa](https://www.conbersa.ai/learn/best-youtube-shorts-hooks) ·
  [Miraflow](https://miraflow.ai/blog/youtube-shorts-best-practices-2026-complete-guide)
- Clickbait-mismatch suppression: [SocialPilot](https://www.socialpilot.co/youtube-marketing/youtube-algorithm) ·
  [Miraflow shadowban](https://miraflow.ai/blog/youtube-shorts-shadowban-2026-how-to-tell-fix)
- AI-slop crackdown / Inauthentic Content Policy: [ScaleLab](https://scalelab.com/en/why-youtube-is-cracking-down-on-ai-generated-content-in-2026) ·
  [MilX](https://milx.app/en/news/why-youtube-just-suspended-thousands-of-ai-channels-and-how-to-protect-yours) ·
  [Nexora](https://nexora-ai.org/blog/youtube-ai-slop-crackdown-2026)
- Voice pricing/free tiers: [Google TTS pricing](https://costbench.com/software/ai-voice-tools/google-cloud-text-to-speech/) ·
  [Azure Indian voices](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/announcing-ga-of-new-indian-voices/4247044) ·
  [ElevenLabs pricing](https://bigvu.tv/blog/elevenlabs-pricing-2026-plans-credits-commercial-rights-api-costs)
- Visuals / faceless niches: [ScaleLab](https://scalelab.com/en/why-youtube-is-cracking-down-on-ai-generated-content-in-2026) ·
  [Outlierkit](https://outlierkit.com/resources/faceless-youtube-channels/)
- Captions: [VocalLab word-highlighting](https://www.vocallab.ai/blog/word-highlighting-subtitles) ·
  [Blitzcut fonts](https://blitzcutai.com/blog/best-caption-fonts-tiktok)
- SEO/metadata: [HashtagTools](https://hashtagtools.io/blog/youtube-hashtags-shorts-seo-guide-2026) ·
  [Touhfa tags](https://touhfa.art/blog/seo/youtube-tags-guide/)
- Format direction: [Pexo](https://pexo.ai/blog/best-ai-video-maker-for-youtube-5424) ·
  [TrueFan India](https://www.truefan.ai/blogs/faceless-youtube-channel-ai-india-2026)
