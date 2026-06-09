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

import hashlib
import logging
import os

from functools import lru_cache

from src import config

log = logging.getLogger(__name__)

# edge-tts (fallback engine)
_VOICE = config.get("VOICE", "en-IN-NeerjaNeural")
_RATE = config.get("VOICE_RATE", "+0%")
_TICKS_PER_SECOND = 1e7  # edge-tts offsets/durations are in 100-nanosecond ticks

# Kokoro (primary engine) — int8 ONNX model files from the kokoro-onnx release.
_KOKORO_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
_KOKORO_MODEL = "kokoro-v1.0.int8.onnx"
_KOKORO_VOICES = "voices-v1.0.bin"


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


def _synthesize_kokoro(text: str, out_path: str) -> float:
    """Write a WAV via Kokoro; return measured duration (s). Raises if no audio."""
    import wave

    import numpy as np

    samples, sr = _kokoro().create(
        text,
        voice=config.get("KOKORO_VOICE", "af_heart"),
        speed=float(config.get("KOKORO_SPEED", "1.0")),
        lang=config.get("KOKORO_LANG", "en-us"),
    )
    if samples is None or len(samples) == 0:
        raise RuntimeError("kokoro produced no audio")
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(pcm.tobytes())
    return len(samples) / float(sr)


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


def synthesize(script_body: str, out_dir: str) -> tuple[str, float]:
    """Return (audio_path, duration_seconds) via Kokoro (humanized) → edge-tts fallback (rule 11).

    Raises ValueError on empty input and RuntimeError only if EVERY engine fails — the
    orchestrator skips that one reel and keeps the batch going (rule 14: soft on runtime).
    """
    text = (script_body or "").strip()
    if not text:
        raise ValueError("voice.synthesize: empty script_body.")
    os.makedirs(out_dir, exist_ok=True)

    engine = str(config.get("VOICE_ENGINE", "kokoro")).lower()
    errors: list[str] = []

    if engine == "kokoro":
        out_path = os.path.join(out_dir, _audio_filename(text, ".wav"))
        try:
            duration = _synthesize_kokoro(text, out_path)
            _log_done(out_path, duration, "kokoro")
            return out_path, duration
        except Exception as e:  # noqa: BLE001 — fall back to edge-tts (rule 11)
            log.warning("voice: kokoro failed (%s); falling back to edge-tts", e)
            errors.append(f"kokoro: {e}")

    out_path = os.path.join(out_dir, _audio_filename(text, ".mp3"))
    try:
        duration = _synthesize_edge_tts(text, out_path, _VOICE, _RATE)
        _log_done(out_path, duration, f"edge-tts:{_VOICE}")
        return out_path, duration
    except Exception as e:  # noqa: BLE001
        errors.append(f"edge-tts: {e}")
    raise RuntimeError("voice.synthesize: all engines failed — " + " | ".join(errors))


def _log_done(out_path: str, duration: float, engine: str) -> None:
    if duration > 60:
        log.warning("voice: narration is %.1fs (>60s) — script likely too long for a Short.", duration)
    log.info("voice: wrote %s (%.1fs, engine=%s)", out_path, duration, engine)
