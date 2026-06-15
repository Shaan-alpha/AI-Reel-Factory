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
import re
import shutil
import subprocess

from functools import lru_cache

from src import config
from src.assembly import _ffmpeg

log = logging.getLogger(__name__)

# Symbols/emoji libass' default font can't render → tofu boxes. Strip them from the burned
# banner only (the YouTube *title* keeps its emoji). Non-BMP chars + common symbol/emoji blocks.
_NON_RENDERABLE = re.compile(
    "[^\u0020-\uffff]"   # astral plane (most emoji)
    "|[\u2190-\u27bf]"   # arrows, technical, dingbats, misc emoji
    "|[\u2b00-\u2bff]"   # misc symbols & arrows
    "|[\ufe00-\ufe0f\u20e3]"  # variation selectors + keycap
)


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


def _clean_caption_word(word: str) -> str:
    """Trim stray leading/trailing punctuation so fragments like '-level' read cleanly."""
    return word.strip().strip("-—–.,;:!?\"'").strip()


def _hook_banner_text(title: str, max_chars: int = 16, max_lines: int = 3) -> str:
    """Turn the punchy title into an UPPERCASE, emoji-free, word-wrapped banner for frame 1.

    Returns the ASS-ready string (lines joined with '\\N'), or '' if nothing renderable
    remains. Strips characters the burn font can't draw so the banner never shows tofu boxes.
    """
    cleaned = _NON_RENDERABLE.sub("", title or "")
    cleaned = _ass_escape(re.sub(r"\s+", " ", cleaned)).upper()
    if not cleaned:
        return ""
    lines: list[str] = []
    cur = ""
    for word in cleaned.split():
        if cur and len(cur) + 1 + len(word) > max_chars:
            lines.append(cur)
            cur = word
            if len(lines) >= max_lines:
                break
        else:
            cur = f"{cur} {word}".strip()
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return "\\N".join(lines)


def _build_events(words: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Group ~CAPTION_WORDS words per caption (default 2) for readability, cleaned of stray
    punctuation, each held until the next group starts (no blank frames)."""
    size = max(1, int(config.get("CAPTION_WORDS", "2")))
    groups = []
    for i in range(0, len(words), size):
        chunk = words[i : i + size]
        text = " ".join(_clean_caption_word(w[2]) for w in chunk).strip()
        if text:
            groups.append([chunk[0][0], chunk[-1][1], text])

    events = []
    for i, (start, end, text) in enumerate(groups):
        nxt = groups[i + 1][0] if i + 1 < len(groups) else end
        end = nxt if nxt > start else start + 0.10
        events.append((start, end, text))
    return events


def _cs(seconds: float) -> int:
    """Seconds → centiseconds, clamped non-negative (the ASS \\kf karaoke-fill unit)."""
    return max(0, int(round(seconds * 100)))


def _karaoke_line(words: list[tuple[float, float, str]]) -> str:
    """Build one phrase's ASS karaoke text: {\\kf<cs>}word per token.

    Each word's fill runs from its start to the NEXT word's start (covers inter-word gaps) so
    the highlight stays synced to speech; the last word uses its own spoken length. Words are
    punctuation-cleaned and ASS-escaped so a stray brace can't break the override."""
    parts = []
    for i, (start, end, raw) in enumerate(words):
        if i + 1 < len(words):
            dur_cs = _cs(max(words[i + 1][0] - start, end - start))
        else:
            dur_cs = _cs(end - start)
        word = _ass_escape(_clean_caption_word(raw))
        if word:
            parts.append(f"{{\\kf{dur_cs}}}{word}")
    return " ".join(parts)


def _ass_header() -> str:
    """Build the ASS header, reading config at call time so env overrides apply.

    The Karaoke style's PrimaryColour is the FILLED colour (highlight) and SecondaryColour the
    pre-fill (white): ASS \\kf sweeps Secondary→Primary as each word is spoken, so the active
    word lights up. Font is the bundled CAPTION_FONT, resolved by libass via fontsdir."""
    font = config.get("CAPTION_FONT", "Montserrat")
    hilite = config.get("CAPTION_HIGHLIGHT_COLOR", "&H0000FFFF")  # ASS &HBBGGRR: yellow
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{font},104,{hilite},&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,640,1
Style: Hook,{font},94,&H0000FFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,8,3,8,60,60,300,1
Style: Card,{font},90,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _card_events(key_points: list[str], total_dur: float, start_after: float,
                 card_dur: float) -> list[tuple[float, float, str]]:
    """Place each key-point card briefly at its beat across (start_after, total_dur].

    Cards are SPARSE — one short flash per point with gaps between — because constant on-screen
    text hurts retention. Returns [(start_s, end_s, text)]; [] if nothing fits."""
    pts = [str(p).strip() for p in (key_points or []) if str(p).strip()]
    span = total_dur - start_after
    if not pts or span <= 0:
        return []
    slot = span / len(pts)
    out: list[tuple[float, float, str]] = []
    for i, p in enumerate(pts):
        center = start_after + slot * (i + 0.5)
        s = max(start_after, center - card_dur / 2)
        e = min(total_dur, s + card_dur)
        out.append((round(s, 3), round(e, 3), p))
    return out


def _build_ass(words: list[tuple[float, float, str]], hook_text: str | None = None,
               key_points: list[str] | None = None, total_dur: float | None = None) -> str:
    """Render the full .ass subtitle file: active-word karaoke captions + an optional frame-1
    hook banner + optional sparse on-screen key-point cards."""
    lines = [_ass_header()]

    # Frame-1 hook banner: the first frame IS the in-feed thumbnail, so a bold top-of-screen
    # hook is the single biggest free CTR lever. Drawn on Layer 1 (top), the word captions sit
    # at the bottom — they don't overlap. Toggle via ENABLE_HOOK_CAPTION; duration HOOK_SECONDS.
    if hook_text and config.get_bool("ENABLE_HOOK_CAPTION", True):
        banner = _hook_banner_text(hook_text)
        if banner:
            secs = float(config.get("HOOK_SECONDS", "1.8"))
            lines.append(
                f"Dialogue: 1,{_format_ts(0)},{_format_ts(secs)},Hook,,0,0,0,,{banner}"
            )

    # Sparse on-screen key-point cards (middle of frame) — story-specific text that lifts the
    # generic-stock B-roll. Shown after the hook window; toggle ENABLE_TEXT_CARDS.
    if key_points and config.get_bool("ENABLE_TEXT_CARDS", True):
        dur = total_dur if total_dur else (words[-1][1] if words else 0.0)
        start_after = float(config.get("HOOK_SECONDS", "1.8"))
        card_dur = float(config.get("CARD_SECONDS", "1.8"))
        for cs, ce, text in _card_events(key_points, dur, start_after, card_dur):
            banner = _hook_banner_text(text, max_chars=18, max_lines=2)
            if banner:
                lines.append(f"Dialogue: 2,{_format_ts(cs)},{_format_ts(ce)},Card,,0,0,0,,{banner}")

    # Group words into short phrases; each phrase is ONE karaoke line whose words fill to the
    # highlight colour exactly as spoken (active-word highlight — a retention driver).
    size = max(1, int(config.get("CAPTION_WORDS", "3")))
    for i in range(0, len(words), size):
        chunk = [w for w in words[i : i + size] if _clean_caption_word(w[2])]
        if not chunk:
            continue
        start, end = chunk[0][0], chunk[-1][1]
        end = end if end > start else start + 0.10
        lines.append(
            f"Dialogue: 0,{_format_ts(start)},{_format_ts(end)},Karaoke,,0,0,0,,{_karaoke_line(chunk)}"
        )
    return "\n".join(lines) + "\n"


def _stage_font(dest_dir: str) -> None:
    """Copy the caption font into dest_dir so the burn (cwd=dest_dir) resolves it via a
    relative `fontsdir=.` — sidesteps Windows drive-colon escaping in the ffmpeg filter.
    Best-effort: libass falls back to a default font if the file is missing (rule 14)."""
    src = config.get("CAPTION_FONT_FILE", os.path.join("assets", "fonts", "Montserrat-Bold.ttf"))
    try:
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(dest_dir, os.path.basename(src)))
    except Exception as e:  # noqa: BLE001 — font staging is best-effort
        log.warning("subtitles: could not stage caption font %s (%s)", src, e)


def _burn(video_path: str, ass_path: str, out_path: str) -> None:
    """Burn the .ass onto the video with FFmpeg. Runs in the subtitle's dir so the filter
    arg is a bare filename — avoids Windows drive-colon/backslash escaping in libass."""
    work_dir = os.path.dirname(os.path.abspath(ass_path))
    _stage_font(work_dir)  # so libass resolves CAPTION_FONT via a relative fontsdir
    cmd = [
        _ffmpeg(), "-y",
        "-i", os.path.abspath(video_path),
        "-vf", f"ass={os.path.basename(ass_path)}:fontsdir=.",
        "-c:a", "copy",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        os.path.abspath(out_path),
    ]
    proc = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"subtitles: ffmpeg burn failed ({proc.returncode}):\n{proc.stderr[-1500:]}")


def burn_captions(video_path: str, audio_path: str, out_path: str,
                  hook_text: str | None = None, key_points: list[str] | None = None) -> str:
    """Transcribe → word-by-word events → burn into video. Return final reel path.

    `hook_text` (the punchy video title) is drawn as a bold banner on frame 1 — the first frame
    is the in-feed thumbnail, so this is the biggest free CTR lever. `key_points` are short
    phrases burned as sparse mid-frame cards (story-specific text). Both optional/back-compatible.
    """
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
    total_dur = words[-1][1] if words else None
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(_build_ass(words, hook_text, key_points, total_dur))

    log.info("subtitles: burning %d word events into %s", len(words), out_path)
    _burn(video_path, ass_path, out_path)
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError("subtitles: ffmpeg reported success but produced no output file.")
    return out_path
