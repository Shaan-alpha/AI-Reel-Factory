"""Module 4 — Voice (narration).

Contract:
    what it does : synthesizes narration audio from a script body.
    input        : script_body (str); output dir.
    output       : (audio_path, duration_seconds).
    depends on   : edge-tts (default). Wrapped so Kokoro can slot in as fallback (rule 11).

Keep it one clear voice for MVP. Target < 60s. edge-tts is unofficial (Microsoft Edge's
online TTS) and free — no API key. Voice/rate are env-overridable (VOICE / VOICE_RATE).

Duration is measured from edge-tts WordBoundary events (end of the last spoken word), so it
excludes a little trailing silence — accurate enough for the <60s gate; assembly (Module 6)
can re-probe the file with FFmpeg if it needs exact length.

The local file is a render artifact: produce it here, let assembly/publish consume it, then
delete it (rule 15 — never store video/audio in Supabase).
"""
from __future__ import annotations

import hashlib
import logging
import os

from src import config

log = logging.getLogger(__name__)

# Indian-English female voice fits the channel; override via env without a code change.
_VOICE = config.get("VOICE", "en-IN-NeerjaNeural")
_RATE = config.get("VOICE_RATE", "+0%")

_TICKS_PER_SECOND = 1e7  # edge-tts offsets/durations are in 100-nanosecond ticks


def _audio_filename(script_body: str) -> str:
    """Deterministic name from the script text → reruns overwrite, never duplicate (rule 12)."""
    digest = hashlib.sha1(script_body.encode("utf-8")).hexdigest()[:12]
    return f"narration_{digest}.mp3"


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
    """Return (audio_path, duration_seconds). Try edge-tts; Kokoro is the Phase-2 fallback.

    Raises ValueError on empty input and RuntimeError if synthesis fails — the orchestrator
    skips that one reel and keeps the batch going (rule 14: soft on runtime).
    """
    text = (script_body or "").strip()
    if not text:
        raise ValueError("voice.synthesize: empty script_body.")

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, _audio_filename(text))

    try:
        duration = _synthesize_edge_tts(text, out_path, _VOICE, _RATE)
    except Exception as e:  # noqa: BLE001 — surface a clear failure; Kokoro fallback is Phase 2
        raise RuntimeError(
            f"voice.synthesize: edge-tts failed ({e}). "
            "Kokoro fallback is Phase 2 (rule 9 / roadmap)."
        ) from e

    if duration > 60:
        log.warning("voice: narration is %.1fs (>60s) — script likely too long for a Short.", duration)
    log.info("voice: wrote %s (%.1fs, voice=%s)", out_path, duration, _VOICE)
    return out_path, duration
