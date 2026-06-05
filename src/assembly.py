"""Module 6 — Assembly (FFmpeg).

Contract:
    what it does : composes B-roll + narration into a 1080x1920 reel (no captions yet).
    input        : audio_path, clip_paths, output path.
    output       : path to assembled .mp4 (H.264, <=60s, 9:16).
    depends on   : ffmpeg-python / FFmpeg binary.

Concat/trim clips to narration length, scale/crop to 1080x1920, light Ken Burns, mux audio,
optional royalty-free music bed. Cut every 5–8s (retention + copyright safety, docs/08 §3).

STATUS: stub.
"""
from __future__ import annotations


def assemble(audio_path: str, clip_paths: list[str], out_path: str) -> str:
    """Build the 1080x1920 reel and return its path. Subtitles are burned in next (Module 7)."""
    raise NotImplementedError("assembly.assemble — see docs/02-implementation-plan.md §7")
