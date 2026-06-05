# Free Tools Reference (2026)

Every tool is free (beyond your existing Claude Pro sub). Limits and links reflect 2026 research.

---

## Ideation brain (trend research + ideas)

| Tool | Notes | Link |
|------|-------|------|
| **Claude Code (Pro)** ★ primary | Official, scripted-use-sanctioned; built-in web search for trend research. Auth via `claude setup-token`. **Never** pipe the OAuth token into custom code (ToS). | https://code.claude.com/docs |
| **Anthropic Routines** | Cloud-scheduled Claude Code; avoids the GH-Actions cron auth bug. | https://www.infoq.com/news/2026/05/anthropic-routines-claude/ |
| Gemini API (fallback) | 1,500 req/day, 1M tok/min — fires only if Claude didn't produce ideas | https://aistudio.google.com/ |
| Groq (fallback) | 14,400 req/day (Llama 3.1‑8B), ~300 tok/s | https://console.groq.com/ |

> ToS: Claude ideation runs **only** via official Claude Code / Routines at individual scale.
> The fallback uses the **free developer APIs** (Gemini/Groq), not Claude.

---

## Scriptwriting

| Tool | Notes | Link |
|------|-------|------|
| **Gemini API** ★ | Primary scriptwriter; well within free limits | https://aistudio.google.com/ |
| Groq | Fast failover | https://console.groq.com/ |
| Claude (optional) | Can write scripts too, but conserve Pro usage | — |

---

## Text-to-Speech (narration)

| Tool | Notes | Link |
|------|-------|------|
| **edge-tts** (default) | Free, natural voices, **unofficial** (can break) | `pip install edge-tts` |
| **Kokoro TTS** (fallback, Phase 2) | Apache‑2.0, 82M params, CPU-capable, 54 voices, 2-voice "debate" | https://github.com/hexgrad/kokoro |
| Piper (alt) | Fully offline, lightweight | https://github.com/rhasspy/piper |

---

## Subtitles ★ in MVP (word-by-word captions)

| Tool | Notes | Link |
|------|-------|------|
| **faster-whisper** (default) | 4× faster, CPU-friendly, word timestamps | https://github.com/SYSTRAN/faster-whisper |
| **WhisperX** (Phase 2 upgrade) | Higher-accuracy word alignment | https://github.com/m-bain/whisperX |

---

## Visuals (B-roll)

| Tool | Notes | Link |
|------|-------|------|
| **Pexels API** | CC0, commercial OK, no attribution, has video | https://www.pexels.com/api/ |
| **Pixabay API** | CC0-like, download & self-host friendly | https://pixabay.com/api/docs/ |
| Coverr | Free AI + stock clips | https://coverr.co/ |
| (Generative video) | Veo/Runway free tiers — rate-capped, **not** for daily volume | — |

---

## Video assembly

| Tool | Notes | Link |
|------|-------|------|
| **FFmpeg** | Concat, crop to 9:16, Ken Burns, audio mux, burn captions | https://ffmpeg.org/ |
| ffmpeg-python | Pythonic wrapper | https://github.com/kkroening/ffmpeg-python |
| MoviePy (alt) | Higher-level, slower | https://github.com/Zulko/moviepy |

---

## Publishing

| Platform | Automation status | Link |
|----------|-------------------|------|
| **YouTube Data API v3** | ✅ Full auto, ~100 uploads/day free quota | https://developers.google.com/youtube/v3 |
| **Instagram Graph API** | ⚠️ Auto after Meta App Review; ~25–50 posts/24h | https://developers.facebook.com/docs/instagram-platform/content-publishing/ |
| **TikTok Content Posting API** | ⚠️ Draft/semi until app audit (2–6 wks) | https://developers.tiktok.com/products/content-posting-api/ |

---

## Orchestration & infra

| Tool | Free limits | Notes | Link |
|------|-------------|-------|------|
| **Anthropic Routines** | Within Pro usage | Schedules the Claude ideation step | https://www.infoq.com/news/2026/05/anthropic-routines-claude/ |
| **GitHub Actions** | Unlimited min (public); ~2,000/mo (private) | Cron in **UTC**; runs the Python production pipeline | https://docs.github.com/actions |
| **Supabase** | 500 MB DB, 1 GB files; pauses after 7 idle days | State/database | https://supabase.com/pricing |
| **Telegram Bot API** | Free | Approval interface | https://core.telegram.org/bots/api |
| Oracle Cloud Free (Phase 5) | 4 OCPU / 24 GB ARM, always-free | ⚠️ may suspend persistent automation | https://www.oracle.com/cloud/free/ |
| n8n self-hosted (Phase 5) | Free, unlimited workflows | Visual orchestration at scale | https://n8n.io/ |

---

## OSS pipelines to study (don't reinvent)

| Repo | What to borrow |
|------|----------------|
| **ShortGPT** | Overall pipeline architecture | https://github.com/RayVentura/ShortGPT |
| **SamurAIGPT / AI-Youtube-Shorts-Generator** | Whisper + vertical crop patterns | https://github.com/SamurAIGPT/AI-Youtube-Shorts-Generator |
| **SaarD00 / AutoShorts** | Gemini + edge-tts + FFmpeg flow | https://github.com/SaarD00/AI-Youtube-Shorts-Generator |
