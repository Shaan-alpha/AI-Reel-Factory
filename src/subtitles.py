"""Module 7 — Subtitles (word-by-word burned-in captions). ★ in MVP

Contract:
    what it does : transcribes narration to word-level timestamps and burns karaoke
                   captions into the reel.
    input        : video_path, audio_path, output path.
    output       : path to the final captioned .mp4.
    depends on   : faster-whisper (WhisperX is the Phase-2 upgrade) + FFmpeg.

Captions are pixel-baked so they survive re-uploads. Style: large, centered/lower-third,
bold, high-contrast with outline. This is a retention driver — it's in the MVP on purpose.

STATUS: stub.
"""
from __future__ import annotations


def burn_captions(video_path: str, audio_path: str, out_path: str) -> str:
    """Transcribe -> word-by-word events -> burn into video. Return final reel path."""
    raise NotImplementedError("subtitles.burn_captions — see docs/02-implementation-plan.md §8")
