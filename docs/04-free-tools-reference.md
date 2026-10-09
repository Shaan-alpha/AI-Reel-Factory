# Free Tools Reference (2026)

Every tool the system uses, what it does today, and its free tier and limits. Most are free.
**Two are billed**, both on Google Cloud project `but-it-matters-tts` and inside the ≤ $5/month
cap (CLAUDE.md rule 2): **Vertex AI** (Gemini text, grounding, the fact-check gate, the
same-voice TTS fallback, and once the music beds) and **Cloud Text-to-Speech** (Chirp 3 HD). A ₹450/month budget on the
billing account alerts at 50/90/100%; it is an alert, not a hard stop. Limits are the providers'
published terms in 2026; numbers measured on this account say so.

---

## Ideation brain (trend research + ideas)

The live engine is **Gemini on Vertex AI**, with Groq picking the stories. A Claude Routine is
optional and dormant: it has never run in production.

| Tool | Role today | Free tier / cost | Link |
|------|-----------|------------------|------|
| **Google News RSS** ★ | The story pool: the India edition's front page plus its WORLD, BUSINESS, TECHNOLOGY and SCIENCE sections (24 headlines by default). Its search feed also tops up an idea's sources. | Free, no key, no quota | https://news.google.com/ |
| Google Trends RSS (`geo=IN`) | Supplementary trend signal | Free, no key, no quota | https://trends.google.com/ |
| **Groq** (`openai/gpt-oss-120b`) | Stage 1: picks N distinct stories from the pool (Groq first). First choice for the other no-web tasks too (hook punch-up, tighten pass, visual keywords) and the failover for ungrounded Gemini calls. Grounded calls have no Groq fallback. `reasoning_effort` low. | Free. This key's limits: 1,000 requests/day, 8,000 tokens/min (Groq's rate-limit headers, 2026-10-09) | https://console.groq.com/ |
| **Gemini on Vertex AI** ★ (billed) | Stage 2: researches the chosen stories in prose with Google Search grounding (`IDEATION_MODEL`, default `gemini-3.5-flash-lite,gemini-3.5-flash`), then writes the JSON ideas from those notes (`gemini-3.8-flash`). Prose is used because Gemini 3.x returns no citations for a JSON reply. | Tokens billed on every call. Grounding: 5,000 search queries/month free across Gemini 3 models, then $14 per 1,000. Keyless auth (ADC locally, Workload Identity Federation in CI). | https://cloud.google.com/vertex-ai/generative-ai/pricing |
| Claude Code / Anthropic Routines (optional, dormant) | Would write `data/daily-ideas.json` (see `routines/ideation.md`, which needs updating before any re-enable). Not part of the running system. | Within the Pro sub | https://code.claude.com/docs |

> ToS (rule 4): Claude ideation may run **only** via official Claude Code / Routines. The Python
> pipeline uses the Gemini and Groq developer APIs, never Claude.

Vertex retires `gemini-2.5-flash`, `-2.5-flash-lite` and `-2.5-pro` on **2026-10-20**; nothing in
CI uses them any more.

---

## Scriptwriting + fact-check

| Tool | Role today | Free tier / cost | Link |
|------|-----------|------------------|------|
| **Gemini on Vertex AI** ★ (billed) | Writes the script (Template N): a grounded write on `GEMINI_GROUNDED_MODEL` (`gemini-3.5-flash-lite,gemini-3.5-flash`), ungrounded calls on `gemini-3.8-flash`. | Billed per token (pricing link above) | `src/scriptwriter.py` |
| **Fact-check gate** on Vertex (billed) | Re-checks every finished script against live search before voicing (`FACTCHECK_MODEL` `gemini-3.5-flash,gemini-3.5-flash-lite`, 2 samples, one repair pass). | About $0.003-0.004 a check. With the grounded write, a reel spends about 7 grounding queries, about 14 with a repair. | `src/factcheck.py` |
| Groq | First choice for the hook punch-up and the tighten pass; failover for the ungrounded calls | Free (limits above) | https://console.groq.com/ |
| **Gemini Developer API** (AI Studio key) | The code's default backend when `GEMINI_USE_VERTEX` is off (a fresh clone, local runs); the workflows turn Vertex on. Its key is required either way (config check, first TTS link). | Free tier, metered **per model**. Daily caps are small (measured: 20 grounded requests/day on `gemini-2.5-flash`). Free grounded search is closed to new projects (2026-09-04). | https://aistudio.google.com/ |

---

## Text-to-Speech (narration)

One male narrator all the way down the chain (rule 11):
**Gemini TTS `gemini-3.1-flash-tts-preview`, voice Zubenelgenubi** (Developer API → Vertex, then
`gemini-2.5-flash-preview-tts` on the Developer API → `gemini-2.5-flash-tts` on Vertex) →
**Chirp 3 HD `en-IN-Chirp3-HD-Zubenelgenubi`** → **edge-tts `en-IN-PrabhatNeural`** → **Kokoro
`am_michael`**. `VOICE_ENGINE` (default `gemini`) picks the first engine. A Telegram alert fires
when a reel leaves the channel voice, and `posts.voice` records the engine.

| Tool | Role today | Free tier / cost | Link |
|------|-----------|------------------|------|
| **Gemini TTS, Developer API** ★ | The channel voice, first attempt | Free tier, per-model daily quota (a 429 was seen 2026-10-09). **Shutdown 2026-11-17** for both models used here; the replacements, `gemini-3.8-flash-tts` and `gemini-3.8-flash-lite-tts`, are on the free tier and await the operator's ear test. | https://ai.google.dev/gemini-api/docs/speech-generation |
| **Gemini TTS on Vertex** (billed) | Same model and voice when the Developer API fails | No free tier. 3.1 Flash TTS: $1 per 1M input tokens, $20 per 1M audio tokens (25 tokens per second of audio). About $0.5/month at the observed failure rate. If the Developer API models shut down before the switch, every reel lands here. | https://cloud.google.com/text-to-speech/pricing |
| **Google Cloud TTS, Chirp 3 HD** (billed) | First fallback after Gemini. v1 REST with an API key (sent in the `X-Goog-Api-Key` header). Skipped if `GOOGLE_TTS_VOICE` is unset. List voices: `tools/list_google_voices.py`. | 1M characters/month free, then $30 per 1M | https://cloud.google.com/text-to-speech |
| **edge-tts** (fallback) | `en-IN-PrabhatNeural` (male). **Unofficial** Microsoft endpoint, so it can break. | Free, no key | `pip install edge-tts` |
| **Kokoro TTS** (last resort) | `am_michael` (male). Apache-2.0, CPU, offline; ~120 MB int8 model; needs `espeak-ng` on Linux. Also voices CI's live render tests. | Free | https://github.com/hexgrad/kokoro |
| Piper (alternative, not used) | Fully offline, lightweight | Free | https://github.com/rhasspy/piper |

---

## Subtitles ★ in MVP (word-by-word captions)

| Tool | Role today | Link |
|------|-----------|------|
| **faster-whisper** (`base`) | Times each word of the narration (FFmpeg decodes the audio); the caption text comes from the approved script. Free, local; the model downloads from Hugging Face on first run. | https://github.com/SYSTRAN/faster-whisper |
| WhisperX (not used) | Higher-accuracy word alignment | https://github.com/m-bain/whisperX |

---

## Visuals (B-roll)

Production sets `VISUAL_SOURCE=ai` (repo variable; the code default is `photos`). Chain: FLUX.2
klein → `flux-1-schnell` → a Pexels photo with Ken Burns (per shot) → Pexels/Pixabay stock video.

| Tool | Role today | Free tier / limits | Link |
|------|-----------|--------------------|------|
| **Cloudflare Workers AI** ★ | Story-specific illustrative images: `@cf/black-forest-labs/flux-2-klein-4b` at a native 768x1344 with per-shot seeds, then `flux-1-schnell` (no seed). Generated 4 at a time + Ken Burns. Needs `CF_API_TOKEN` + `CF_ACCOUNT_ID`. | Free: 10,000 neurons/day (an estimated ~103 per klein image; a reel uses about 11-12) | https://developers.cloudflare.com/workers-ai/ |
| **Pexels API** | Photo fallback per shot; stock video. Required key. Pexels License (**not CC0**): commercial use OK, no attribution; identifiable people may not appear in a bad light. | Free: 200 requests/hour, 20,000/month | https://www.pexels.com/api/ |
| **Pixabay API** | Stock-video backup. Pixabay Content License (**not CC0**): commercial use OK, no attribution; no misleading use of recognisable people. | Free: 100 requests per 60 s per key; results must be cached for 24 h | https://pixabay.com/api/docs/ |
| Coverr (not used) | Free AI + stock clips | — | https://coverr.co/ |
| Generative video (not used) | Veo/Runway free tiers are rate-capped, not for daily volume | — | — |

---

## Music

| Tool | Role today | Cost | Link |
|------|-----------|------|------|
| Google **Lyria 2** (`lyria-002`) on Vertex (billed) | Generated the four calm beds in `assets/music` once (2026-09-29). Not part of the daily pipeline; the description discloses AI-generated music. | One-off, $0.66 in total | `tools/generate_music_beds.py` |

---

## Video assembly

| Tool | Notes | Link |
|------|-------|------|
| **FFmpeg** (binary, called directly) | 1080x1920 H.264: Ken Burns, crossfades, grade, vignette (grain off by default), music bed with ducking, loudness to -14 LUFS, logo bug, burned captions (libass). CI installs apt's FFmpeg on the pinned `ubuntu-24.04` runner; `ubuntu-latest` moves to 26.04 (FFmpeg 8.0.1) from 2026-10-19. | https://ffmpeg.org/ |
| ffmpeg-python (not used) | Pythonic wrapper | https://github.com/kkroening/ffmpeg-python |
| MoviePy (not used) | Higher-level, slower | https://github.com/Zulko/moviepy |

---

## Publishing

| Platform | Automation status | Link |
|----------|-------------------|------|
| **YouTube Data API v3** | ✅ Full auto: `videos.insert` with the synthetic-content flag; ~100 uploads/day. Analytics reads public stats with `videos.list` (no YouTube Analytics API). Token scopes in use: `youtube.upload`, `youtube.readonly`. | https://developers.google.com/youtube/v3 |
| **Instagram Graph API** | ⚠️ Phase 3. Auto after Meta App Review; ~25–50 posts/24h | https://developers.facebook.com/docs/instagram-platform/content-publishing/ |
| **TikTok Content Posting API** | ⚠️ Phase 3. Draft/semi until app audit (2–6 wks) | https://developers.tiktok.com/products/content-posting-api/ |

---

## Orchestration & infra

| Tool | Free limits | Notes | Link |
|------|-------------|-------|------|
| **GitHub Actions** | Unlimited minutes on a public repo (this one is public); 2,000 min/month on a private repo (Free plan) | Runs the pipeline **on demand** (`make-short`); daily `tests` and `analytics` schedules, which GitHub starts hours late. All runners pinned to `ubuntu-24.04`. GitHub disables a public repo's schedules after 60 days without a commit; `analytics.yml` re-enables them. | https://docs.github.com/actions |
| **Supabase** | 500 MB DB; pauses after 7 days idle | State/database (5 tables, RLS on). The daily `analytics` writes keep it awake. No video stored (rule 15). | https://supabase.com/pricing |
| **Telegram Bot API** | Free | The digest, alerts and published links; the control bot's webhook | https://core.telegram.org/bots/api |
| **Vercel** (Hobby) | Free (1M function invocations/month included) | Hosts the control bot (`telegram-bot/`). Vercel's fair-use terms restrict Hobby to non-commercial personal use; check this before the channel is monetized. | https://vercel.com/docs/limits/fair-use-guidelines |
| Anthropic Routines (optional, dormant) | Within Pro usage | Would schedule the Claude ideation step; not used | https://code.claude.com/docs |
| Oracle Cloud Free (Phase 5) | 4 OCPU / 24 GB ARM, always-free | ⚠️ may suspend persistent automation | https://www.oracle.com/cloud/free/ |
| n8n self-hosted (Phase 5) | Free, unlimited workflows | Visual orchestration at scale | https://n8n.io/ |

---

## Dead options (do not re-try)

| Tool | Status |
|------|--------|
| GitHub Models | Retired: every call returns HTTP 410 (`github_models_retirement_brownout`, checked 2026-09-01). Leave `ENABLE_GH_MODELS` and `PREFER_GH_MODELS` off; turning them on only adds a failing call. |
| Google Custom Search JSON API | Closed to new customers; Google discontinues it on 2027-01-01. |
| A second free Gemini key for grounding | Free grounded search is closed to new Google Cloud projects (2026-09-04), so a new key cannot ground. |

---

## OSS pipelines to study (don't reinvent)

| Repo | What to borrow | Link |
|------|----------------|------|
| **ShortGPT** | Overall pipeline architecture | https://github.com/RayVentura/ShortGPT |
| **SamurAIGPT / AI-Youtube-Shorts-Generator** | Whisper + vertical crop patterns | https://github.com/SamurAIGPT/AI-Youtube-Shorts-Generator |
| **SaarD00 / AutoShorts** | Gemini + edge-tts + FFmpeg flow | https://github.com/SaarD00/AI-Youtube-Shorts-Generator |
