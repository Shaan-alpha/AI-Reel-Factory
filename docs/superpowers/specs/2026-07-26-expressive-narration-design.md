# Expressive narration: sarcasm the viewer can actually hear

**Date:** 2026-07-26
**Status:** Approved (design) — ready for implementation plan
**Scope:** `src/voice.py`, `src/scriptwriter.py`, `tools/compare_voices.py` (new), their tests,
`.env.example` + both workflows. **No DB schema change, no downstream module change.**

## Problem

The channel's identity is a dry, sarcastic narrator, but the narration does not *sound* sarcastic.
The 2026-07-26 overhaul added `voice._clean_tts_text()` to strip `[sarcastic]` / `[sigh]` /
`<sfx:...>` tags "before TTS synthesis" — but **nothing in the pipeline emits those tags**, and
the operator confirmed the intent was real expressive delivery, not a no-op sanitiser.

### Diagnosis (evidence-backed)

1. **`_synthesize_google` sends `input.text`** — the plainest input mode the API offers. No markup,
   no style instruction, no pace control.
2. **Emotion tags are not a Chirp 3 HD feature**, so on our current engine the tag would either be
   read aloud or (with the sanitiser) silently dropped. Either way: no change in delivery.
3. **The operator's instinct was right, just aimed at the wrong engine.** Inline audio tags
   (`[whispers]`, `[excited]`, `[laughs]`) are a **documented feature of the Gemini Developer API
   TTS models** — and Chirp 3 HD separately supports `[pause short|pause|pause long]` via its
   `markup` input field.
4. **`ENABLE_DRAMATIC_PACING` only runs on Kokoro**, the *last* fallback. The primary voice has no
   timing control at all — the knob approximates on the worst engine what better engines do natively.

### What each API actually offers (verified)

| Field / feature | Applies to | What it gives us |
|---|---|---|
| `text` | all voices | what we send today — no control |
| `markup` | **Chirp 3 HD only** ("may not be used with any other voices") | `[pause short]`, `[pause]`, `[pause long]` |
| `audioConfig.speakingRate` | Chirp | 0.25–2.0 pace |
| `prompt` (Cloud TTS) | promptable models only (Cloud Gemini-TTS) | free-text Style Instructions |
| **inline audio tags + director's notes** | **Gemini Developer API TTS** | `[sarcastic]`-style tags, style/accent/pace/tone control, 30 voices incl. `Kore` |

### Cost (rule 2) — the free path wins

Gemini Developer API TTS pricing, free tier:

| Model | Free tier | Paid |
|---|---|---|
| **`gemini-2.5-flash-preview-tts`** | **input free, output free** | $0.50/1M in · $10/1M audio out |
| `gemini-3.1-flash-tts-preview` | input free, output free | $1/1M in · $20/1M audio out |
| `gemini-2.5-pro-preview-tts` | **none** | $1/1M in · $20/1M audio out |

For reference, the Cloud TTS route would have cost ~$1.05/mo (Flash) or ~$2.10/mo (Pro) at
150 reels × 28 s × 25 audio-tokens/s = 105,000 audio tokens/month.

**The chosen route costs $0** and reuses the existing `GEMINI_API_KEY` and the already-pinned
`google-genai==2.8.0` — no new credential, no new dependency, no billing account, no rule-2
stop-and-flag. Rule 4 is untouched: this is the Gemini developer API, never Claude.

> Note for the operator: **Google One AI Pro / Gemini Advanced is a consumer subscription and does
> not pay for Google Cloud Platform API usage.** GCP trial credits do. This design avoids the
> question entirely by staying on the free developer-API tier.

## Decisions (from brainstorming)

- **Layered approach**: writing + timing + pace on the free Chirp path, then a promptable engine
  for true vocal delivery. Chosen over "Chirp only" (never sounds sarcastic, only pauses well) and
  over "replace Chirp entirely" (weakens rule 11's fallback chain).
- **Layer 3 uses the Gemini Developer API, not Cloud TTS Gemini-TTS.** Same capability, better:
  free, existing key, existing SDK, and it supports the inline emotion tags the operator wanted.
  Cloud TTS Gemini-TTS is documented below as the paid upgrade path if free limits bind.
- **Default `gemini-2.5-flash-preview-tts`** — the only TTS model that is free on both input and
  output. `gemini-2.5-pro-preview-tts` has **no free tier**, so it is opt-in only.
- **Style is a tuned constant plus sparse inline tags**, not per-script LLM-generated style
  (YAGNI): one well-written `VOICE_STYLE_PROMPT` beats a generated one and costs no extra call.

## Design

### Layer 1 — Writing (free, improves every engine)

`_PROMPT_N` gains a WRITE FOR THE VOICE block from Google's documented Chirp scripting practice:
ellipses (`...`) for deliberate pauses and hesitation, short sentences, contractions, strategic
punctuation (periods = full stop, commas = short pause), breaking complex sentences.

Plain text, so it survives **every** engine — the only layer that also lifts edge-tts and Kokoro
when the chain falls back.

### Layer 2 — Inline tags (the operator's original intent, now real)

The scriptwriter emits two tag families, both sparse:

- **Emotion/delivery tags** — e.g. `[sarcastic]`, `[deadpan]`, `[dry]` — consumed by the Gemini
  TTS engine.
- **Pause tags** — `[pause short|pause|pause long]` — consumed by Chirp 3 HD's `markup` field.

Handling is per-engine, from one script body:

| Engine | Treatment |
|---|---|
| Gemini TTS | tags pass through (they are the feature) |
| Chirp 3 HD | pause tags → `input.markup`; emotion tags stripped |
| edge-tts / Kokoro | all tags stripped by `_clean_tts_text` (today's behaviour) |

- New pure function `voice._to_markup(text) -> str`, no network, fully unit-testable.
- **Strict allow-lists** per engine. An invented tag is stripped, never sent — it must not 400 the
  API or get read aloud.
- **Caps enforced in code, not just requested in the prompt**: `MAX_PAUSE_TAGS` (default 3) and
  `MAX_STYLE_TAGS` (default 3). The prompt asks; the guard is what makes it true.
- `_synthesize_google` sends `input.markup` **only when** the voice is Chirp 3 HD *and* a valid
  pause tag is present; otherwise the request is byte-identical to today's.
- Toggled by `ENABLE_PAUSE_MARKUP` (default on — free and reversible).

### Layer 3 — Vocal delivery (Gemini Developer API, free)

New engine `gemini`, resolved by the existing `VOICE_ENGINE` knob, at the head of the chain:

```
gemini -> google (Chirp 3 HD) -> edge-tts -> kokoro
```

- `_synthesize_gemini(text, out_dir) -> (path, seconds)` — the **same contract as every other
  engine**, so the fallback chain needs no special-casing (rule 7).
- Uses the already-pinned `google-genai` SDK and the existing `GEMINI_API_KEY`.
- `GEMINI_TTS_MODEL` default `gemini-2.5-flash-preview-tts`; `GEMINI_TTS_VOICE` default `Kore`
  (matches the current Chirp voice character). Note the name format differs from Chirp's
  (`Kore`, not `en-IN-Chirp3-HD-Kore`) — hence a separate knob.
- `VOICE_STYLE_PROMPT` default: *"Deliver with dry, deadpan sarcasm — amused, never zany. Land the
  final line straight."*
- **SDK surface verified present in the pinned `google-genai==2.8.0`** — no dependency bump:
  `types.SpeechConfig`, `types.VoiceConfig`, `types.PrebuiltVoiceConfig`, and
  `GenerateContentConfig.speech_config` / `.response_modalities` all exist.
- Call shape is `models.generate_content(model=…, contents=…, config=GenerateContentConfig(
  response_modalities=["AUDIO"], speech_config=SpeechConfig(voice_config=…)))`.
- **The response is raw PCM (24 kHz, 16-bit mono), not a WAV container.** It must be wrapped with
  the stdlib `wave` module before use; duration is then measured exactly as `_synthesize_google`
  does today. Getting this wrong yields a file ffprobe cannot read.

### Layer 4 — Pace

`GOOGLE_TTS_SPEAKING_RATE`, clamped to [0.25, 2.0], into `audioConfig.speakingRate` on the Chirp
path. Slightly above 1.0 suits Shorts retention.

`ENABLE_DRAMATIC_PACING` stays Kokoro-only — it is a sample-level concat that only makes sense
where we hold raw samples. Layers 2 and 4 give the Google path its own, better timing.

### Contract impact

- `script_body`'s **shape is unchanged** (it may now contain tags) → no DB migration, no change to
  `db.insert_script`, `production`, `publish`, or `subtitles`.
- **Captions cannot leak tags**: `subtitles` runs whisper over the rendered *audio*, not the script
  text, so a tag that never reaches the synthesiser can never reach the screen.
- **Must fix as part of this:** the scriptwriter's `SCRIPT_MAX_WORDS` guard would count
  `[pause long]` as two words and corrupt the 25–30s length enforcement. Tags are stripped before
  counting.
- Any surface that displays `script_body` verbatim (e.g. a Telegram debug echo) shows tags; that is
  cosmetic and accepted.

## Error handling (rules 11, 13, 14)

| Failure | Behaviour |
|---|---|
| Unknown/malformed tag | stripped by the allow-list, never sent |
| Chirp rejects the markup | **retry once as plain `input.text`** before falling through, so a markup surprise never costs us the good voice |
| Gemini TTS fails / quota-exhausted | log + fall through to Chirp → edge → kokoro |
| Gemini TTS preview model withdrawn | same fallback; `GEMINI_TTS_MODEL` is a knob, so recovery is a repo-variable change, not a deploy |
| Every engine fails | unchanged: `RuntimeError`, orchestrator skips that reel and keeps the batch |

**Quota contention (rule 13) — the main risk.** This project has already exhausted Gemini free RPD
once (2026-06-10: "RPD hit 30/20"), and grounded ideation/scriptwriting is Gemini-only and
accuracy-critical. TTS must never starve it. Mitigations:

1. `GEMINI_TTS_API_KEY` falls back to `GEMINI_API_KEY`, so the operator can isolate TTS onto a
   second free key without a code change.
2. TTS failure is fail-soft to Chirp, which is free and unaffected.
3. Load is small: ~5 calls/day versus ideation's batch.

## Testing

**Unit (no network):** per-engine allow-lists; tag caps enforced; `_clean_tts_text` still strips
tags for edge/Kokoro; word count excludes tags; request-body shape for the Chirp-markup path;
`_synthesize_gemini` called with the right model/voice/style (mocked SDK); chain order with
`VOICE_ENGINE=gemini`; markup-rejected-retries-as-text; quota failure falls through to Chirp.

**Live (gated, as with the existing live tests):** real Chirp markup synthesis, and real Gemini TTS
synthesis. Both behind explicit env flags so CI stays deterministic and quota-safe.

**Operator tool:** `tools/compare_voices.py` synthesizes one script through Chirp and Gemini TTS
into labelled WAVs so the choice is settled by ear, not by assumption. Mirrors the existing
`tools/list_google_voices.py` pattern.

## Rollout

Ships **inert**: `VOICE_ENGINE` stays `google`, so behaviour is byte-identical until the operator
runs the A/B and flips the knob. New config in `.env.example` and both workflows:
`VOICE_STYLE_PROMPT`, `GEMINI_TTS_MODEL`, `GEMINI_TTS_VOICE`, `GEMINI_TTS_API_KEY`,
`GOOGLE_TTS_SPEAKING_RATE`, `ENABLE_PAUSE_MARKUP`, `MAX_PAUSE_TAGS`, `MAX_STYLE_TAGS`.

## Open risks

1. **Free-tier rate limits for the TTS models are unpublished** — the docs defer to the AI Studio
   dashboard. Verify actual RPM/RPD before relying on it, and prefer a separate key
   (`GEMINI_TTS_API_KEY`) if TTS shares a pool with text generation.
2. **All developer-API TTS models are preview.** Acceptable only because Chirp remains the
   fallback (rule 11); never make a preview model the sole path.
3. ~~`google-genai==2.8.0` may predate the TTS speech-generation surface.~~ **Resolved 2026-07-26:**
   verified the pinned version exposes `SpeechConfig` / `VoiceConfig` / `PrebuiltVoiceConfig` and
   `GenerateContentConfig.speech_config`. No dependency change needed.
4. Free-tier usage on the developer API may be used to improve Google's products. Our content is
   public YouTube narration, so the sensitivity is low — but it is a conscious acceptance.

## Rejected alternative (kept for the record)

**Cloud TTS Gemini-TTS** (`gemini-2.5-pro-tts` via the Cloud TTS REST endpoint, ~$2.10/month).
Equivalent style control via the `prompt` field, but: costs money where the developer API is free,
needs a GCP billing account, would require verifying that REST + API-key auth supports
`prompt`/`model_name` (the docs show the Python client with ADC), and has **no inline emotion-tag
support**. It remains the documented upgrade path if the free tier's limits prove too tight.
