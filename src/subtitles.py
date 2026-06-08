"""Module 7 — Subtitles (word-by-word burned-in captions). ★ in MVP

Contract:
    what it does : transcribes narration to word-level timestamps and burns karaoke
                   captions into the reel.
    input        : video_path, audio_path, output path.
    output       : path to the final captioned .mp4.
    depends on   : faster-whisper (WhisperX is the Phase-2 upgrade) + FFmpeg.

Captions are pixel-baked so they survive re-uploads. Style: large, centered/lower-third,
bold, high-contrast with a thick outline — this is a retention driver, in the MVP on purpose.

One word shows at a time (true word-by-word), each timed to its spoken moment and held until
the next word starts so there's never a blank frame. Model size is env-overridable
(WHISPER_MODEL, default 'base'); CPU int8 for the free-tier runner.
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess

from functools import lru_cache

from src import config
from src.assembly import _ffmpeg

log = logging.getLogger(__name__)


@lru_cache(maxsize=2)
def _load_model(size: str):
    """Load (once) a CPU int8 faster-whisper model. Imported lazily; downloads on first use."""
    from faster_whisper import WhisperModel

    return WhisperModel(size, device="cpu", compute_type="int8")


def _transcribe_words(audio_path: str) -> list[tuple[float, float, str]]:
    """Return [(start_s, end_s, word)] for the narration. Isolated for testability."""
    model = _load_model(config.get("WHISPER_MODEL", "base"))
    segments, _info = model.transcribe(
        audio_path, word_timestamps=True, beam_size=5, language="en", vad_filter=True,
    )
    words: list[tuple[float, float, str]] = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append((float(w.start), float(w.end), text))
    return words


def _format_ts(seconds: float) -> str:
    """Seconds → ASS timestamp H:MM:SS.cc (centiseconds)."""
    cs = max(0, int(round(seconds * 100)))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    """Strip characters that would break ASS override/braces; collapse newlines."""
    return text.replace("\\", "").replace("{", "").replace("}", "").replace("\n", " ").strip()


def _build_events(words: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Hold each word until the next starts (no blank frames); last keeps its own end."""
    events = []
    for i, (start, end, word) in enumerate(words):
        nxt = words[i + 1][0] if i + 1 < len(words) else end
        end = nxt if nxt > start else start + 0.10
        events.append((start, end, word))
    return events


_ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pop,Arial,112,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,640,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _build_ass(words: list[tuple[float, float, str]]) -> str:
    """Render the full .ass subtitle file (one Dialogue per word)."""
    lines = [_ASS_HEADER]
    for start, end, word in _build_events(words):
        lines.append(
            f"Dialogue: 0,{_format_ts(start)},{_format_ts(end)},Pop,,0,0,0,,{_ass_escape(word)}"
        )
    return "\n".join(lines) + "\n"


def _burn(video_path: str, ass_path: str, out_path: str) -> None:
    """Burn the .ass onto the video with FFmpeg. Runs in the subtitle's dir so the filter
    arg is a bare filename — avoids Windows drive-colon/backslash escaping in libass."""
    work_dir = os.path.dirname(os.path.abspath(ass_path))
    cmd = [
        _ffmpeg(), "-y",
        "-i", os.path.abspath(video_path),
        "-vf", f"ass={os.path.basename(ass_path)}",
        "-c:a", "copy",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        os.path.abspath(out_path),
    ]
    proc = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"subtitles: ffmpeg burn failed ({proc.returncode}):\n{proc.stderr[-1500:]}")


def burn_captions(video_path: str, audio_path: str, out_path: str) -> str:
    """Transcribe → word-by-word events → burn into video. Return final reel path."""
    if not os.path.exists(video_path):
        raise ValueError(f"subtitles: video not found: {video_path}")
    if not os.path.exists(audio_path):
        raise ValueError(f"subtitles: audio not found: {audio_path}")

    words = _transcribe_words(audio_path)
    if not words:
        raise RuntimeError("subtitles: transcription produced no words — cannot caption reel.")

    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    digest = hashlib.sha1(os.path.abspath(audio_path).encode("utf-8")).hexdigest()[:12]
    ass_path = os.path.join(out_dir, f"captions_{digest}.ass")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(_build_ass(words))

    log.info("subtitles: burning %d word events into %s", len(words), out_path)
    _burn(video_path, ass_path, out_path)
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError("subtitles: ffmpeg reported success but produced no output file.")
    return out_path
