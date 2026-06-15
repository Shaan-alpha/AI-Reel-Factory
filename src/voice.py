"""Module 4 — Voice (narration).

Contract:
    what it does : synthesizes narration audio from a script body.
    input        : script_body (str); output dir.
    output       : (audio_path, duration_seconds).
    depends on   : Kokoro (primary, humanized) → edge-tts (fallback) (rule 11).

Default engine is **Kokoro** (open-weight, Apache-2.0, runs on CPU via kokoro-onnx) for a
far more natural/human voice; edge-tts is the always-available fallback. Pick via VOICE_ENGINE
(kokoro|edge-tts). Kokoro voice/speed via KOKORO_VOICE/KOKORO_SPEED; edge-tts via VOICE/VOICE_RATE.
Kokoro's int8 model (~120 MB) auto-downloads once to KOKORO_CACHE.

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
    body = {
        "input": {"text": text},
        "voice": {"languageCode": lang, "name": voice_name},
        "audioConfig": {"audioEncoding": "LINEAR16"},
    }
    r = requests.post(_GOOGLE_TTS_URL, params={"key": api_key}, json=body, timeout=60)
    if r.status_code != 200:
        # Surface Google's actual reason (invalid/blocked key, byte limit, etc.) so the chain's
        # fallback warning is actionable instead of an opaque "400 Client Error".
        raise RuntimeError(f"google tts HTTP {r.status_code}: {r.text[:300]}")
    b64 = (r.json() or {}).get("audioContent")
    if not b64:
        raise RuntimeError("google tts: empty audioContent")

    out_path = os.path.join(out_dir, _audio_filename(text, ".wav"))
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(b64))
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


_ENGINE_ORDER = ("google", "edge", "kokoro")
# Accept friendly/legacy values for VOICE_ENGINE.
_ENGINE_ALIASES = {"edge-tts": "edge", "chirp": "google", "google-tts": "google"}


def _engine_google(text: str, out_dir: str) -> tuple[str, float]:
    path, dur = _synthesize_google(text, out_dir)
    _log_done(path, dur, "google:chirp3hd")
    return path, dur


def _engine_edge(text: str, out_dir: str) -> tuple[str, float]:
    out_path = os.path.join(out_dir, _audio_filename(text, ".mp3"))
    dur = _synthesize_edge_tts(text, out_path, _VOICE, _RATE)
    _log_done(out_path, dur, f"edge-tts:{_VOICE}")
    return out_path, dur


def _engine_kokoro(text: str, out_dir: str) -> tuple[str, float]:
    out_path = os.path.join(out_dir, _audio_filename(text, ".wav"))
    dur = _synthesize_kokoro(text, out_path)
    _log_done(out_path, dur, "kokoro")
    return out_path, dur


def synthesize(script_body: str, out_dir: str) -> tuple[str, float]:
    """Return (audio_path, duration_seconds) via an ordered fallback chain (rule 11):
    google (Chirp 3 HD) → edge-tts (en-IN) → kokoro. VOICE_ENGINE picks the primary engine;
    the remaining engines follow as fallbacks. Engines are resolved by name at call time, so a
    missing key/model just advances to the next link.

    Raises ValueError on empty input, RuntimeError only if EVERY engine fails — the orchestrator
    skips that one reel and keeps the batch going (rule 14: soft on runtime).
    """
    text = (script_body or "").strip()
    if not text:
        raise ValueError("voice.synthesize: empty script_body.")
    os.makedirs(out_dir, exist_ok=True)

    primary = str(config.get("VOICE_ENGINE", "google")).lower()
    primary = _ENGINE_ALIASES.get(primary, primary)
    order = [primary] + [e for e in _ENGINE_ORDER if e != primary]

    errors: list[str] = []
    for name in order:
        fn = globals().get(f"_engine_{name}")
        if fn is None:
            continue
        try:
            return fn(text, out_dir)
        except Exception as e:  # noqa: BLE001 — try the next engine in the chain (rule 11)
            log.warning("voice: engine %s failed (%s); trying next", name, e)
            errors.append(f"{name}: {e}")
    raise RuntimeError("voice.synthesize: all engines failed — " + " | ".join(errors))


def _log_done(out_path: str, duration: float, engine: str) -> None:
    if duration > 60:
        log.warning("voice: narration is %.1fs (>60s) — script likely too long for a Short.", duration)
    log.info("voice: wrote %s (%.1fs, engine=%s)", out_path, duration, engine)
