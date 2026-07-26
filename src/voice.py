"""Module 4 — Voice (narration).

Contract:
    what it does : synthesizes narration audio from a script body.
    input        : script_body (str); output dir.
    output       : (audio_path, duration_seconds).
    depends on   : Gemini Developer API TTS → Google Cloud TTS (Chirp 3 HD) → edge-tts → Kokoro
                   (rule 11: every engine has a fallback behind it).

Default engine is **Gemini TTS** on the free `gemini-2.5-flash-preview-tts` model, voice
**Zubenelgenubi** ("Casual") — chosen by ear because it carries dry sarcasm, which is the
channel's whole register. The chain falls through to Chirp 3 HD, then edge-tts, then Kokoro,
resolved by name at call time so a missing key or a withdrawn preview model just advances a
link. Pick the primary via VOICE_ENGINE (gemini|google|edge|kokoro).

**Expressive delivery is per-engine**, because the control signals are not portable:
  · `gemini`  — promptable: honours VOICE_STYLE_PROMPT *and* inline style tags ([sarcastic]).
                Free tier is metered per model: 3 RPM / 10 RPD (measured 2026-07-27), so it
                cannot starve the grounded ideation that shares the same API key.
  · `google`  — Chirp 3 HD reads `[pause]` tags, but only through its `markup` input field,
                and supports GOOGLE_TTS_SPEAKING_RATE.
  · `edge`/`kokoro` — no tag support at all; every tag is stripped before synthesis.
So each engine filters the script body itself rather than being handed pre-stripped text.

Kokoro's int8 model (~120 MB) auto-downloads once to KOKORO_CACHE; its voice/speed come from
KOKORO_VOICE/KOKORO_SPEED, edge-tts from VOICE/VOICE_RATE.

The local file is a render artifact: produce it here, let assembly/publish consume it, then
delete it (rule 15 — never store video/audio in Supabase).
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import re

from functools import lru_cache

import requests

from src import config

log = logging.getLogger(__name__)

# Split on sentence enders (incl. ellipsis) so dramatic pacing can put a beat between sentences.
_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")

# edge-tts (fallback engine)
_VOICE = config.get("VOICE", "en-IN-NeerjaNeural")
_RATE = config.get("VOICE_RATE", "+0%")
_TICKS_PER_SECOND = 1e7  # edge-tts offsets/durations are in 100-nanosecond ticks

# Kokoro (primary engine) — int8 ONNX model files from the kokoro-onnx release.
_KOKORO_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
_KOKORO_MODEL = "kokoro-v1.0.int8.onnx"
_KOKORO_VOICES = "voices-v1.0.bin"

# Google Cloud TTS (primary engine) — Chirp 3 HD via the v1 REST endpoint + API key (headless).
_GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

# Gemini Developer API TTS returns raw PCM at this rate (16-bit mono, no container).
_GEMINI_TTS_RATE = 24000
# Structured per Google's own style-prompt guidance: an audio profile, then director's notes on
# pacing and inflection, then paralinguistic detail. Their docs are explicit that naming an
# emotion ("sarcastic") underperforms describing what it SOUNDS like -- and for this channel the
# failure mode is a narrator who announces the joke, so most of this prompt is restraint.
_DEFAULT_STYLE_PROMPT = (
    "You are a sharp, faintly unimpressed news explainer talking to one friend, not an audience. "
    "Read at a brisk clip with crisp consonants and very little warmth. "
    "Deliver the setup flat and factual; let the dry amusement sit UNDER the words rather than on "
    "top of them, and never announce the joke. Understate the punchline instead of leaning into "
    "it, with a slight downward inflection at the end of each sentence. "
    "Read the final line completely straight, as though it plainly matters."
)


def _audio_filename(script_body: str, ext: str = ".mp3") -> str:
    """Deterministic name from the script text → reruns overwrite, never duplicate (rule 12)."""
    digest = hashlib.sha1(script_body.encode("utf-8")).hexdigest()[:12]
    return f"narration_{digest}{ext}"


def _download(url: str, dest: str) -> None:
    import requests

    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    f.write(chunk)


def _ensure_kokoro_models() -> tuple[str, str]:
    """Return (model_path, voices_path), downloading the int8 model once if missing."""
    cache = config.get("KOKORO_CACHE", os.path.join(os.path.expanduser("~"), ".cache", "kokoro"))
    os.makedirs(cache, exist_ok=True)
    paths = []
    for name in (_KOKORO_MODEL, _KOKORO_VOICES):
        dest = os.path.join(cache, name)
        if not (os.path.exists(dest) and os.path.getsize(dest) > 1000):
            log.info("voice: downloading Kokoro asset %s …", name)
            _download(_KOKORO_BASE + name, dest)
        paths.append(dest)
    return paths[0], paths[1]


@lru_cache(maxsize=1)
def _kokoro():
    """Load (once) the Kokoro ONNX model. Imported lazily so edge-only setups don't need it."""
    from kokoro_onnx import Kokoro

    model, voices = _ensure_kokoro_models()
    return Kokoro(model, voices)


def _split_sentences(text: str) -> list[str]:
    """Split narration into sentences for dramatic pacing. Always ≥1 item for non-empty input."""
    return [s.strip() for s in _SENTENCE_RE.split(text.strip()) if s.strip()]


def _synthesize_kokoro(text: str, out_path: str) -> float:
    """Write a WAV via Kokoro; return measured duration (s). Raises if no audio.

    With dramatic pacing on (ENABLE_DRAMATIC_PACING, default), each sentence is synthesized
    separately and joined with a short silence — a LONGER beat before the final payoff line — so
    the delivery breathes and lands the punchline instead of running on. Kokoro returns raw
    samples, so this is exact, in-memory, and needs no ffmpeg. Single-sentence scripts (and any
    paced-synth error) use one shot; the outer fallback still covers a total Kokoro failure (rule 11)."""
    import wave

    import numpy as np

    k = _kokoro()
    voice_name = config.get("KOKORO_VOICE", "af_heart")
    speed = float(config.get("KOKORO_SPEED", "1.0"))
    lang = config.get("KOKORO_LANG", "en-us")

    def _create(piece: str):
        samples, sr = k.create(piece, voice=voice_name, speed=speed, lang=lang)
        if samples is None or len(samples) == 0:
            raise RuntimeError("kokoro produced no audio")
        return np.asarray(samples, dtype=np.float32), int(sr)

    sentences = _split_sentences(text) if config.get_bool("ENABLE_DRAMATIC_PACING", True) else [text]
    try:
        if len(sentences) <= 1:
            samples, sr = _create(text)
        else:
            gap = float(config.get("PAUSE_BETWEEN", "0.18"))
            payoff_gap = float(config.get("PAUSE_BEFORE_PAYOFF", "0.5"))
            pieces, sr = [], 0
            for i, sentence in enumerate(sentences):
                chunk, sr = _create(sentence)
                pieces.append(chunk)
                if i < len(sentences) - 1:  # silence after every sentence except the last
                    secs = payoff_gap if i == len(sentences) - 2 else gap  # longer before payoff
                    pieces.append(np.zeros(int(sr * secs), dtype=np.float32))
            samples = np.concatenate(pieces)
    except Exception as e:  # noqa: BLE001 — paced synth is best-effort; retry one-shot before edge
        log.warning("voice: paced kokoro synth failed (%s); using one-shot.", e)
        samples, sr = _create(text)

    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(pcm.tobytes())
    return len(samples) / float(sr)


def _is_chirp_voice(name: str) -> bool:
    """`markup` is Chirp 3 HD-only — sending it with any other voice is an API error."""
    return "chirp3-hd" in (name or "").lower()


def _speaking_rate() -> float | None:
    """audioConfig.speakingRate, clamped to the documented [0.25, 2.0]. None = leave unset."""
    raw = (config.get("GOOGLE_TTS_SPEAKING_RATE", "") or "").strip()
    if not raw:
        return None
    try:
        return max(0.25, min(float(raw), 2.0))
    except (TypeError, ValueError):
        log.warning("voice: GOOGLE_TTS_SPEAKING_RATE=%r is not a number; ignoring", raw)
        return None


def _synthesize_google(text: str, out_dir: str) -> tuple[str, float]:
    """Synthesize via Google Cloud TTS Chirp 3 HD (REST + API key). Returns (wav_path, seconds).

    Requests LINEAR16 so the response bytes are a real WAV we measure with the stdlib `wave`
    module (exact, no ffprobe). Raises — so the chain falls back — if the key/voice is unset
    or the API errors."""
    import wave

    api_key = (config.get("GOOGLE_TTS_API_KEY", "") or "").strip()
    voice_name = (config.get("GOOGLE_TTS_VOICE", "") or "").strip()
    if not api_key or not voice_name:
        raise RuntimeError("google tts: GOOGLE_TTS_API_KEY / GOOGLE_TTS_VOICE not set")

    lang = config.get("GOOGLE_TTS_LANGUAGE", "en-IN")

    # Chirp 3 HD reads pause tags — but only via the dedicated `markup` input field, and only on
    # Chirp voices (the API rejects `markup` for anything else). Style tags are Gemini's and are
    # stripped here so they can't be read aloud.
    clean = _clean_tts_text(text)
    markup = _pause_markup(text) if config.get_bool("ENABLE_PAUSE_MARKUP", True) else ""
    use_markup = _is_chirp_voice(voice_name) and _has_pause_tag(markup)

    audio_cfg: dict = {"audioEncoding": "LINEAR16"}
    rate = _speaking_rate()
    if rate is not None:
        audio_cfg["speakingRate"] = rate

    def _post(payload_input: dict):
        return requests.post(
            _GOOGLE_TTS_URL,
            params={"key": api_key},
            json={"input": payload_input,
                  "voice": {"languageCode": lang, "name": voice_name},
                  "audioConfig": audio_cfg},
            timeout=60,
        )

    r = _post({"markup": markup} if use_markup else {"text": clean})
    if r.status_code != 200 and use_markup:
        # Fail-soft (rules 11, 14): an unexpected markup rejection should cost us the comic
        # timing, never the good voice — retry the request the plain way before failing over.
        log.warning("voice: Chirp rejected markup (HTTP %d); retrying as plain text.", r.status_code)
        r = _post({"text": clean})
    if r.status_code != 200:
        # Surface Google's actual reason (invalid/blocked key, byte limit, etc.) so the chain's
        # fallback warning is actionable instead of an opaque "400 Client Error".
        raise RuntimeError(f"google tts HTTP {r.status_code}: {r.text[:500]}")
    b64 = (r.json() or {}).get("audioContent")
    if not b64:
        raise RuntimeError("google tts: empty audioContent")

    out_path = os.path.join(out_dir, _audio_filename(clean, ".wav"))
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(b64))
    with wave.open(out_path, "rb") as w:
        duration = w.getnframes() / float(w.getframerate())
    return out_path, duration


def _synthesize_gemini(text: str, out_dir: str) -> tuple[str, float]:
    """Synthesize via the Gemini Developer API TTS models. Returns (wav_path, seconds).

    Uses the already-pinned google-genai SDK and the existing GEMINI_API_KEY, so this adds no
    dependency and no new credential. Style comes from VOICE_STYLE_PROMPT plus the inline style
    tags the scriptwriter emits — both are features of this API, unlike Chirp, which is why
    the emotion tags finally do something here.

    GEMINI_TTS_API_KEY (optional) isolates TTS onto a second free key so it cannot starve the
    grounded ideation/scriptwriting that only Gemini can do (rule 13).

    Default model is the FREE one. gemini-2.5-pro-preview-tts has no free tier, so selecting it
    is a deliberate act, not a default.
    """
    import wave

    from google import genai
    from google.genai import types

    key = (config.get("GEMINI_TTS_API_KEY") or config.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("gemini tts: GEMINI_TTS_API_KEY / GEMINI_API_KEY not set")

    spoken = _style_text(text)  # keep style tags, drop Chirp's pause tags
    style = config.get("VOICE_STYLE_PROMPT", _DEFAULT_STYLE_PROMPT)
    model = config.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
    # Zubenelgenubi ("Casual") was chosen by ear over Kore/Schedar/Algenib/Charon — it is the
    # channel's voice identity now, not an incidental default. Re-pick via tools/tune_voice.py.
    voice_name = config.get("GEMINI_TTS_VOICE", "Zubenelgenubi")

    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=model,
        contents=f"{style}\n\n{spoken}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
        ),
    )
    try:
        pcm = resp.candidates[0].content.parts[0].inline_data.data
    except (AttributeError, IndexError, TypeError) as e:
        raise RuntimeError(f"gemini tts: unexpected response shape ({e})") from e
    if not pcm:
        raise RuntimeError("gemini tts: empty audio")

    # The response is RAW PCM, not a WAV container — without this wrapper nothing downstream
    # (ffprobe, assembly, whisper) can read the file.
    out_path = os.path.join(out_dir, _audio_filename(spoken, ".wav"))
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_GEMINI_TTS_RATE)
        w.writeframes(pcm)
    with wave.open(out_path, "rb") as w:
        duration = w.getnframes() / float(w.getframerate())
    return out_path, duration


def _stream_chunks(text: str, voice: str, rate: str):
    """Yield edge-tts stream chunks (audio + WordBoundary). Isolated for testability."""
    import edge_tts

    comm = edge_tts.Communicate(text, voice, rate=rate)
    yield from comm.stream_sync()


def _synthesize_edge_tts(text: str, out_path: str, voice: str, rate: str) -> float:
    """Write MP3 to out_path; return measured duration (s). Raises if no audio came back."""
    last_end_ticks = 0
    wrote_audio = False
    with open(out_path, "wb") as f:
        for chunk in _stream_chunks(text, voice, rate):
            if chunk["type"] == "audio":
                f.write(chunk["data"])
                wrote_audio = True
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                # edge-tts emits SentenceBoundary by default (7.x); either gives offset+duration.
                last_end_ticks = max(last_end_ticks, chunk["offset"] + chunk["duration"])
    if not wrote_audio:
        raise RuntimeError("edge-tts returned no audio (check voice name / connectivity).")
    return last_end_ticks / _TICKS_PER_SECOND


# "gemini" is deliberately ABSENT from this tuple. synthesize() builds the chain as
# [primary] + [the rest], so leaving it out means the Gemini engine is prepended only when it is
# explicitly selected, and does not appear at all under the default VOICE_ENGINE=google. Adding
# it here would silently put it in the fallback path for every Chirp failure.
_ENGINE_ORDER = ("google", "edge", "kokoro")
# Accept friendly/legacy values for VOICE_ENGINE.
_ENGINE_ALIASES = {"edge-tts": "edge", "chirp": "google", "google-tts": "google",
                   "gemini-tts": "gemini"}


def _engine_gemini(text: str, out_dir: str) -> tuple[str, float]:
    path, dur = _synthesize_gemini(text, out_dir)
    _log_done(path, dur, f"gemini:{config.get('GEMINI_TTS_MODEL', 'gemini-2.5-flash-preview-tts')}")
    return path, dur


def _engine_google(text: str, out_dir: str) -> tuple[str, float]:
    path, dur = _synthesize_google(text, out_dir)
    _log_done(path, dur, "google:chirp3hd")
    return path, dur


def _engine_edge(text: str, out_dir: str) -> tuple[str, float]:
    clean = _clean_tts_text(text)  # no tag support: a tag here would be read aloud
    out_path = os.path.join(out_dir, _audio_filename(clean, ".mp3"))
    dur = _synthesize_edge_tts(clean, out_path, _VOICE, _RATE)
    _log_done(out_path, dur, f"edge-tts:{_VOICE}")
    return out_path, dur


def _engine_kokoro(text: str, out_dir: str) -> tuple[str, float]:
    clean = _clean_tts_text(text)  # no tag support
    out_path = os.path.join(out_dir, _audio_filename(clean, ".wav"))
    dur = _synthesize_kokoro(clean, out_path)
    _log_done(out_path, dur, "kokoro")
    return out_path, dur


# Inline bracket tags the scriptwriter may emit, in two families consumed by different engines:
#   pause tags -> Chirp 3 HD's `markup` input field
#   style tags -> Gemini TTS inline audio tags
# Everything outside these allow-lists is stripped. An invented tag must never reach an API
# (it 400s the request) nor the synthesiser (it gets read aloud).
_PAUSE_TAGS = ("pause short", "pause", "pause long")
_STYLE_TAGS = ("sarcastic", "deadpan", "dry", "amused", "flat", "sighs", "laughs", "beat")

_TAG_RE = re.compile(r"\[([^\]]{1,24})\]|<[^>]{1,60}>")


def _tag_limit(key: str, default: int) -> int:
    try:
        return max(0, int(config.get(key, str(default))))
    except (TypeError, ValueError):
        return default


def _filter_tags(text: str, keep: tuple[str, ...], limit: int) -> str:
    """Keep at most `limit` allow-listed bracket tags; strip every other tag.

    The cap is enforced HERE rather than trusted to the prompt: a prompt asks, a guard is what
    makes it true. Over-tagging a 25-30s Short reads as sluggish."""
    kept = 0

    def _sub(m: re.Match) -> str:
        nonlocal kept
        inner = m.group(1)
        if inner is not None:
            token = inner.strip().lower()
            if token in keep and kept < limit:
                kept += 1
                return f"[{token}]"
        return ""

    return re.sub(r"\s+", " ", _TAG_RE.sub(_sub, text)).strip()


def _clean_tts_text(text: str) -> str:
    """Strip every tag — for engines with no tag support (edge-tts, Kokoro)."""
    return _filter_tags(text, (), 0)


def _pause_markup(text: str) -> str:
    """Chirp 3 HD `markup`: keep pause tags, drop style tags."""
    return _filter_tags(text, _PAUSE_TAGS, _tag_limit("MAX_PAUSE_TAGS", 3))


def _style_text(text: str) -> str:
    """Gemini TTS input: keep style tags, drop pause tags."""
    return _filter_tags(text, _STYLE_TAGS, _tag_limit("MAX_STYLE_TAGS", 3))


def _has_pause_tag(text: str) -> bool:
    return bool(re.search(r"\[(?:pause short|pause long|pause)\]", text))


def synthesize(script_body: str, out_dir: str) -> tuple[str, float]:
    """Return (audio_path, duration_seconds) via an ordered fallback chain (rule 11):
    google (Chirp 3 HD) → edge-tts (en-IN) → kokoro. VOICE_ENGINE picks the primary engine;
    the remaining engines follow as fallbacks. Engines are resolved by name at call time, so a
    missing key/model just advances to the next link.

    Raises ValueError on empty input, RuntimeError only if EVERY engine fails — the orchestrator
    skips that one reel and keeps the batch going (rule 14: soft on runtime).
    """
    # Tags are NOT stripped here: each engine filters for itself, because which tags are
    # meaningful depends on the engine (Chirp reads pause tags, Gemini reads style tags, edge-tts
    # and Kokoro read neither). Stripping up front is what made the tags a no-op before.
    raw = (script_body or "").strip()
    if not _clean_tts_text(raw):  # tags alone are stage direction, not narration
        raise ValueError("voice.synthesize: empty script_body.")
    os.makedirs(out_dir, exist_ok=True)

    primary = str(config.get("VOICE_ENGINE", "gemini")).lower()
    primary = _ENGINE_ALIASES.get(primary, primary)
    order = [primary] + [e for e in _ENGINE_ORDER if e != primary]

    errors: list[str] = []
    for name in order:
        fn = globals().get(f"_engine_{name}")
        if fn is None:
            continue
        try:
            return fn(raw, out_dir)
        except Exception as e:  # noqa: BLE001 — try the next engine in the chain (rule 11)
            log.warning("voice: engine %s failed (%s); trying next", name, e)
            errors.append(f"{name}: {e}")
    raise RuntimeError("voice.synthesize: all engines failed — " + " | ".join(errors))


def _log_done(out_path: str, duration: float, engine: str) -> None:
    if duration > 60:
        log.warning("voice: narration is %.1fs (>60s) — script likely too long for a Short.", duration)
    log.info("voice: wrote %s (%.1fs, engine=%s)", out_path, duration, engine)
