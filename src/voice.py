"""Module 4 — Voice (narration).

Contract:
    what it does : synthesizes narration audio from a script body.
    input        : script_body (str); output dir.
    output       : (audio_path, duration_seconds).
    depends on   : edge-tts (default). Wrapped so Kokoro can slot in as fallback (rule 11).

Keep it one clear voice for MVP. Target < 60s. edge-tts is unofficial (rule 11: fallback).

STATUS: stub.
"""
from __future__ import annotations


def synthesize(script_body: str, out_dir: str) -> tuple[str, float]:
    """Return (audio_path, duration_seconds). Try edge-tts, fall back to Kokoro later."""
    raise NotImplementedError("voice.synthesize — see docs/02-implementation-plan.md §5")
