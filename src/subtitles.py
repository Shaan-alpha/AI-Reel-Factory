"""Module 7 — Subtitles (word-by-word burned-in captions). ★ in MVP

Contract:
    what it does : transcribes narration to word-level timestamps and burns karaoke
                   captions into the reel.
    input        : video_path, audio_path, output path.
    output       : path to the final captioned .mp4.
    depends on   : faster-whisper (WhisperX is the Phase-2 upgrade) + FFmpeg;
                   src.graphics (Pillow) only on the optional ENABLE_GRAPHIC_CARDS path.

Captions are pixel-baked so they survive re-uploads. Style: large, centered/lower-third,
bold, high-contrast with a thick outline — this is a retention driver, in the MVP on purpose.

One word shows at a time (true word-by-word), each timed to its spoken moment and held until
the next word starts so there's never a blank frame. Model size is env-overridable
(WHISPER_MODEL, default 'base'); CPU int8 for the free-tier runner.
"""
from __future__ import annotations

import difflib
import hashlib
import logging
import os
import re
import shutil
import subprocess

from collections import Counter
from functools import lru_cache

from src import config
from src.text import split_sentences
from src.assembly import BT709_TAGS, RENDER_TIMEOUT_SECONDS, _ffmpeg, x264_args
from src.text import ends_clause

log = logging.getLogger(__name__)

# Symbols/emoji libass' default font can't render → tofu boxes. Strip them from the burned
# banner only (the YouTube *title* keeps its emoji). Non-BMP chars + common symbol/emoji blocks.
# Inline delivery tags the scriptwriter emits for the TTS engine ([pause], [sarcastic], ...).
# They are stage direction for the voice and must never be drawn on screen.
_DELIVERY_TAG = re.compile(r"\[[^\]]{0,24}\]")

_NON_RENDERABLE = re.compile(
    "[^\u0020-\uffff]"   # astral plane (most emoji)
    "|[\u2190-\u27bf]"   # arrows, technical, dingbats, misc emoji
    "|[\u2b00-\u2bff]"   # misc symbols & arrows
    "|[\ufe00-\ufe0f\u20e3]"  # variation selectors + keycap
)


@lru_cache(maxsize=2)
def _load_model(size: str):
    """Load (once) a CPU int8 faster-whisper model. Imported lazily; downloads on first use.

    The local cache is tried first: a plain load asks the Hugging Face Hub for the file list
    every time, so a Hub outage or rate limit failed the caption step with the model cached."""
    from faster_whisper import WhisperModel

    try:
        return WhisperModel(size, device="cpu", compute_type="int8", local_files_only=True)
    except Exception:  # noqa: BLE001 — not cached yet: fetch it
        return WhisperModel(size, device="cpu", compute_type="int8")


_WHISPER_RATE = 16000


def _decode_for_whisper(audio_path: str):
    """The narration as 16 kHz mono float32, decoded by the FFmpeg binary the pipeline needs
    anyway. Given a file path, faster-whisper decodes through PyAV, and PyAV 19 rejected the call
    it makes: every reel from 2026-10-01 died here. Given an array it never touches PyAV."""
    import numpy as np

    proc = subprocess.run(
        [_ffmpeg(), "-v", "error", "-nostdin", "-i", audio_path, "-f", "f32le", "-ac", "1",
         "-ar", str(_WHISPER_RATE), "-"],
        capture_output=True, timeout=120,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"ffmpeg could not decode {audio_path}: "
                           f"{proc.stderr.decode('utf-8', 'replace')[-300:]}")
    return np.frombuffer(proc.stdout, dtype=np.float32)


# A whisper token that CONTINUES the previous number rather than starting a new word: a comma or
# period immediately followed by a digit (",270", ".4"), the second half of a range ("-5"), or a
# bare percent sign. '3-5% drop' was burned as '3 5 %' on r2YTZ1GAtbE.
_NUMBER_CONTINUATION = re.compile(r"^(?:[.,\-–]\d|%$)")


def _merge_number_tokens(
        words: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Rejoin a figure faster-whisper split across word tokens ('1' + ',270' -> '1,270').

    Word-level timestamps break "1,270" into '1' and ',270' and "2.4" into '2' and '.4'.
    `_clean_caption_word` then strips the leading punctuation, so the burned captions read
    "authority 1" / "270 people died" and "and 2 4" — i.e. the reel states a different number
    from the one the narrator says and the fact-check gate approved. Measured on real narration
    2026-09-03; the audio itself is faithful, so the fix belongs here and not in voice.py.

    Merges only when the previous token ENDS IN A DIGIT, so an ordinary sentence-ending token
    ("likes.") never swallows what follows it.
    """
    merged: list[tuple[float, float, str]] = []
    for start, end, text in words:
        if merged and _NUMBER_CONTINUATION.match(text) and merged[-1][2][-1:].isdigit():
            prev_start, _prev_end, prev_text = merged[-1]
            merged[-1] = (prev_start, end, prev_text + text)
        else:
            merged.append((start, end, text))
    return merged


def _transcribe_words(audio_path: str) -> list[tuple[float, float, str]]:
    """Return [(start_s, end_s, word)] for the narration. Isolated for testability."""
    model = _load_model(config.get("WHISPER_MODEL", "base"))
    try:
        audio = _decode_for_whisper(audio_path)
    except Exception as e:  # noqa: BLE001 — faster-whisper's own decoder is still a fallback
        log.warning("subtitles: FFmpeg decode failed (%s); letting faster-whisper decode", e)
        audio = audio_path
    segments, _info = model.transcribe(
        audio, word_timestamps=True, beam_size=5, language="en", vad_filter=True,
    )
    words: list[tuple[float, float, str]] = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append((float(w.start), float(w.end), text))
    return _merge_number_tokens(words)


def _norm(token: str) -> str:
    """A token reduced to what ASR and the script can agree on: lowercase letters and digits."""
    return re.sub(r"[^a-z0-9]", "", token.lower())


def _script_tokens(script_text: str | None) -> list[str]:
    """The script's spoken words, as the captions show them: delivery tags removed, and split on
    dashes too ('drama—it' is two spoken words and needs two karaoke timings)."""
    text = re.sub(r"\s*[—–]\s*", " ", _DELIVERY_TAG.sub(" ", script_text or ""))
    return [t for t in text.split() if _norm(t)]


def _first_sentence_end(words: list[tuple[float, float, str]],
                        script_text: str | None) -> float | None:
    """When the narration's first sentence ends: the aligned word that ends it, counted in the
    captions' own tokens. None without words or a script."""
    if not words or not script_text:
        return None
    sentences = split_sentences(_DELIVERY_TAG.sub(" ", script_text))
    n = len(_script_tokens(sentences[0])) if sentences else 0
    return words[min(n, len(words)) - 1][1] if n else None


def _align_to_script(words: list[tuple[float, float, str]],
                     script_text: str | None) -> list[tuple[float, float, str]]:
    """Caption the SCRIPT's words at whisper's timings.

    The burned captions used to be whatever faster-whisper heard: 7.6% of words differed from
    the fact-checked script over 10 published reels, including numbers ('3-5% drop' -> '3 5 %',
    'A 769-crore defense deal' -> 'A 769 croned') and meaning ('Unofficially' -> 'On
    officially'). The script is what was approved and what the narrator read, so whisper is
    kept for WHEN each word is spoken and the script supplies WHAT it is.

    difflib aligns the two token streams: matched and substituted runs take the script's text
    with the heard timing (spread by length when the counts differ); script words whisper
    missed are slotted into the gap before the next heard word; words only whisper heard are
    dropped. If the two barely agree, the script is not what was spoken, so the ASR words are
    returned untouched.
    """
    spoken = _script_tokens(script_text)
    if not words or not spoken:
        return words
    heard = [_norm(w[2]) for w in words]
    matcher = difflib.SequenceMatcher(None, heard, [_norm(t) for t in spoken], autojunk=False)
    if matcher.ratio() < 0.6:
        log.warning("subtitles: script and narration disagree (match %.2f); captioning the ASR",
                    matcher.ratio())
        return words
    out: list[tuple[float, float, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "delete":
            continue
        tokens = spoken[j1:j2]
        if tag in ("equal", "replace") and i2 > i1:
            if tag == "equal":
                out.extend((words[i1 + k][0], words[i1 + k][1], tokens[k])
                           for k in range(len(tokens)))
                continue
            start, end = words[i1][0], words[i2 - 1][1]
        else:  # insert: script words whisper did not hear
            start = out[-1][1] if out else (words[i1][0] if i1 < len(words) else 0.0)
            end = words[i1][0] if i1 < len(words) else start + 0.3 * len(tokens)
            end = max(end, start + 0.05 * len(tokens))
        weights = [max(1, len(_norm(t))) for t in tokens]
        total, t0 = float(sum(weights)), start
        for token, w in zip(tokens, weights):
            t1 = t0 + (end - start) * w / total
            out.append((t0, t1, token))
            t0 = t1
    return out


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


def _wrap(words: list[str], max_chars: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for word in words:
        if cur and len(cur) + 1 + len(word) > max_chars:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines


def _hook_banner_text(title: str, max_chars: int = 16, max_lines: int = 3,
                      base_size: int = 94) -> str:
    """Turn the punchy title into an UPPERCASE, emoji-free, word-wrapped banner for frame 1.

    Returns the ASS-ready string (lines joined with '\\N'), or '' if nothing renderable
    remains. Strips characters the burn font can't draw so the banner never shows tofu boxes.

    The text is FITTED, not cut: the font steps down (an inline \\fs override) until every
    word fits in `max_lines`. The old version stopped at the last full line and threw the rest
    away with no ellipsis, which truncated 20 of the last 40 banners mid-phrase ('...CLAIM: WHY
    IT', '...TRADE UNDER'). Only a title too long even at the smallest size is cut, at a word,
    with an ellipsis.
    """
    # Strip inline delivery tags FIRST. The scriptwriter is instructed to emit [pause]/[sarcastic],
    # and if one leaks into the title or a key point it would be BURNED onto the video as literal
    # "[SARCASTIC]" — brackets are plain ASCII, so _NON_RENDERABLE does not catch them.
    cleaned = _DELIVERY_TAG.sub(" ", title or "")
    cleaned = _NON_RENDERABLE.sub("", cleaned)
    # "MINUTE—WHY" is one unbreakable word to the wrapper; spaced, the dash can end a line.
    cleaned = re.sub(r"\s*[—–]\s*", " — ", cleaned)
    cleaned = _ass_escape(re.sub(r"\s+", " ", cleaned)).upper()
    if not cleaned:
        return ""
    words = cleaned.split()
    # Down to 0.58 (55 px at the hook's 94): still legible on a phone, and enough for a 7-word
    # title that word-wrapping pushed onto a fourth line at 0.72 (local render, 2026-09-27).
    scales = (1.0, 0.89, 0.8, 0.72, 0.64, 0.58)
    for scale in scales:
        chars = int(max_chars / scale)
        lines = _wrap(words, chars)
        if len(lines) <= max_lines:
            size = int(round(base_size * scale))
            text = "\\N".join(lines)
            return text if scale == 1.0 else f"{{\\fs{size}}}{text}"
    lines = _wrap(words, int(max_chars / scales[-1]))[:max_lines]
    return (f"{{\\fs{int(round(base_size * scales[-1]))}}}"
            + "\\N".join(lines).rstrip(" :,;-") + "…")


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


# libass draws the bundled Montserrat at 0.632x the width PIL measures at the same size
# (calibrated 2026-09-27 on three real renders, 0.630-0.632). Karaoke is 104 px.
_LIBASS_WIDTH = 0.632
_KARAOKE_PX = 104
# 1080 minus MarginL 90 and MarginR 150: the right-hand 120 px is the Shorts action rail.
_MAX_CAPTION_PX = 840


@lru_cache(maxsize=1)
def _caption_font():
    try:
        from PIL import ImageFont

        return ImageFont.truetype(config.get(
            "CAPTION_FONT_FILE", os.path.join("assets", "fonts", "Montserrat-Bold.ttf")),
            _KARAOKE_PX)
    except Exception:  # noqa: BLE001 — fall back to a character estimate
        return None


def _caption_px(text: str) -> float:
    font = _caption_font()
    if font is not None:
        return font.getlength(text) * _LIBASS_WIDTH
    return len(text) * _KARAOKE_PX * 0.36  # Montserrat Bold averages about 0.57 em a glyph


def _caption_groups(words: list[tuple[float, float, str]],
                    size: int) -> list[list[tuple[float, float, str]]]:
    """Up to `size` words per caption, never across a sentence end, never wider than the safe
    width. Fixed chunks of 3 put 13% of captions across a sentence break ('matters When news')
    and ran 1% off the frame ('Germany's ThyssenKrupp Marine' is 1130 px)."""
    groups: list[list[tuple[float, float, str]]] = []
    cur: list[tuple[float, float, str]] = []
    for w in words:
        if not _clean_caption_word(w[2]):
            continue
        trial = " ".join(_clean_caption_word(x[2]) for x in [*cur, w])
        if cur and (len(cur) >= size or _caption_px(trial) > _MAX_CAPTION_PX):
            groups.append(cur)
            cur = []
        cur.append(w)
        if ends_clause(w[2]):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


# The longest pause a caption is held across (seconds).
_HOLD_GAP = 0.6
# English subtitles on Hinglish reels (design 7.7): plain white, smaller than the karaoke, at the
# karaoke's height, inside the Shorts safe box (x 48-888, bottom at y 1248), clear of the rail.
_SUB_PX = 86


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
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{font},104,{hilite},&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,2,48,192,672,1
Style: Hook,{font},94,&H0000FFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,8,3,8,60,60,300,1
Style: Card,{font},90,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,5,40,40,0,1
Style: Source,{font},46,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3,2,8,60,60,300,1
Style: Sub,{font},{_SUB_PX},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,48,192,672,1
Style: Number,{font},150,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,8,3,8,60,60,760,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _spoken_at(point: str, words: list[tuple[float, float, str]], after: float) -> float | None:
    """When the narration first says a distinctive word of `point`, after `after`; else None."""
    wanted = {_norm(t) for t in point.split() if len(_norm(t)) > 3 or _norm(t).isdigit()}
    for start, _end, text in words or []:
        if start >= after and _norm(text) in wanted:
            return start
    return None


def _card_events(key_points: list[str], total_dur: float, start_after: float,
                 card_dur: float,
                 words: list[tuple[float, float, str]] | None = None) -> list[tuple[float, float, str]]:
    """Place each key-point card briefly at its beat across (start_after, total_dur].

    Cards are SPARSE — one short flash per point with gaps between — because constant on-screen
    text hurts retention. Returns [(start_s, end_s, text)]; [] if nothing fits."""
    pts = [str(p).strip() for p in (key_points or []) if str(p).strip()]
    span = total_dur - start_after
    if not pts or span <= 0:
        return []
    slot = span / len(pts)
    out: list[tuple[float, float, str]] = []
    cursor = start_after
    for i, p in enumerate(pts):
        # On the beat where the point is SAID when it can be found (audit 2026-09-27: evenly
        # spaced cards flashed a number seconds before or after the narration reached it);
        # otherwise the old even slot.
        heard = _spoken_at(p, words, cursor)
        center = start_after + slot * (i + 0.5)
        s = heard if heard is not None else max(start_after, center - card_dur / 2)
        s = max(s, cursor)
        e = min(total_dur, s + card_dur)
        if e - s < 0.5:
            continue
        out.append((round(s, 3), round(e, 3), p))
        cursor = e
    return out


def _graphic_cards_enabled() -> bool:
    """PIL stat cards instead of ASS text cards. Default OFF: the ASS cards already ship and
    work, so this is a look change the operator opts into for a run and judges, not a silent
    switch on a live channel."""
    return config.get_bool("ENABLE_GRAPHIC_CARDS", False)


def _render_graphic_cards(key_points: list[str] | None, total_dur: float,
                          work_dir: str) -> list[tuple[float, float, str]]:
    """Render each key point as a PIL stat-card PNG. Returns [(start_s, end_s, png_path)].

    Shares `_card_events` with the ASS path so both treatments use ONE timing rule. Returns []
    when disabled or on any failure, and the caller then falls back to the ASS text cards —
    a card renderer breaking must never cost us the captions (rules 11, 14)."""
    if not (key_points and config.get_bool("ENABLE_TEXT_CARDS", False) and _graphic_cards_enabled()):
        return []
    try:
        from src import graphics

        start_after = float(config.get("HOOK_SECONDS", "1.8"))
        card_dur = float(config.get("CARD_SECONDS", "1.8"))
        out: list[tuple[float, float, str]] = []
        for i, (cs, ce, text) in enumerate(_card_events(key_points, total_dur, start_after, card_dur)):
            png = os.path.join(work_dir, f"card_{i}.png")
            graphics.create_stat_card(text, png)
            out.append((cs, ce, png))
        return out
    except Exception as e:  # noqa: BLE001 — fall back to the ASS text cards
        log.warning("subtitles: graphic cards failed (%s); using ASS text cards instead", e)
        return []


# The key-number card (design 11.5): a short scale-in, on screen for its spoken length plus half
# a second, between 1.5 and 2.5 s.
_NUMBER_SCALE_IN = "{\\fscx70\\fscy70\\t(0,180,\\fscx100\\fscy100)}"
_NUMBER_MIN, _NUMBER_TAIL, _NUMBER_MAX = 1.5, 0.5, 2.5


def _token_run(wanted: list[str], tokens: list[str]) -> int | None:
    """Where the run `wanted` first starts in `tokens` (both normalized), or None."""
    n = len(wanted)
    if not n:
        return None
    return next((i for i in range(len(tokens) - n + 1) if tokens[i:i + n] == wanted), None)


def _number_tokens(key_number: str | None) -> list[str]:
    """The key number as the captions' normalized tokens: "Rs 2,000 crore" -> rs 2000 crore."""
    return [_norm(t) for t in _script_tokens(key_number)]


def _number_moment_words(key_number: str | None,
                         words: list[tuple[float, float, str]]) -> tuple[float, float] | None:
    """When the narration says the key number: the first run of aligned words that spell it,
    whole tokens only, so "2" never matches inside "2,000". None when it is not said."""
    wanted = _number_tokens(key_number)
    i = _token_run(wanted, [_norm(w[2]) for w in words or []])
    return None if i is None else (words[i][0], words[i + len(wanted) - 1][1])


def _number_moment_blocks(key_number: str | None,
                          blocks: list[tuple[float, float, str]]) -> tuple[float, float] | None:
    """The first English subtitle block that carries the key number: a Hinglish narration has
    no word timings, so the block is when its part of the sentence is spoken."""
    wanted = _number_tokens(key_number)
    for start, end, block in blocks or []:
        if _token_run(wanted, [_norm(t) for t in _script_tokens(block)]) is not None:
            return start, end
    return None


def _number_card(key_number: str | None, moment: tuple[float, float] | None,
                 total_dur: float) -> tuple[float, float, str] | None:
    """(start, end, ASS text) of the key-number card, from the moment it is said, never past
    the reel's end. None when it is not said or too little time is left to read it."""
    if not (key_number and moment):
        return None
    start, said_end = moment
    shown = min(_NUMBER_MAX, max(_NUMBER_MIN, said_end - start + _NUMBER_TAIL))
    end = min(total_dur, start + shown)
    if end - start < 0.5:
        return None
    return start, end, _NUMBER_SCALE_IN + _ass_escape(_NON_RENDERABLE.sub("", key_number)).upper()


def _banner_seconds(first_end: float | None) -> float:
    """How long the banner shows: until the first sentence ends, at least HOOK_SECONDS (1.8)
    and at most HOOK_MAX_SECONDS (4.0). It vanished at 1.8 s, the biggest change between two
    frames in the test reels (design 11.5)."""
    low = float(config.get("HOOK_SECONDS", "1.8"))
    high = max(low, float(config.get("HOOK_MAX_SECONDS", "4.0")))
    return min(high, max(low, first_end or 0.0))


_BANNER_TOP = 300  # the Hook style's MarginV: just under the Shorts top bar (288 px)


def _source_margin(banner: str) -> int:
    """The source line's distance from the top: under the banner's real rows at its real size,
    or at the banner's own top when there is no banner."""
    if not banner:
        return _BANNER_TOP
    size = re.search(r"\\fs(\d+)", banner)
    rows = banner.count("\\N") + 1
    return int(_BANNER_TOP + rows * (int(size.group(1)) if size else 94) * 1.25 + 16)


def _build_ass(words: list[tuple[float, float, str]], hook_text: str | None = None,
               key_points: list[str] | None = None, total_dur: float | None = None,
               source_label: str | None = None, first_end: float | None = None,
               number: tuple[float, float, str] | None = None) -> str:
    """Render the full .ass subtitle file: active-word karaoke captions, the banner (the title)
    and the source line for the first sentence (`first_end`, when known), and optional sparse
    key-point cards. Everything sits inside the Shorts safe area (design 11.5)."""
    lines = [_ass_header()]
    banner = (_hook_banner_text(hook_text)
              if hook_text and config.get_bool("ENABLE_HOOK_CAPTION", True) else "")
    banner_end = _banner_seconds(first_end)

    # The source citation, with the first sentence: the claim it supports (rule 6: cite
    # sources). Under the banner, at the top: at y 1480 the Shorts interface covered it.
    if source_label and config.get_bool("ENABLE_SOURCE_CITE", True):
        until = (max(float(config.get("HOOK_SECONDS", "1.8")), first_end) if first_end
                 else float(config.get("SOURCE_CITE_SECONDS", "3.0")))
        label = _ass_escape(_NON_RENDERABLE.sub("", f"Source: {source_label}"))
        lines.append(f"Dialogue: 1,{_format_ts(0)},{_format_ts(until)},Source,,0,0,"
                     f"{_source_margin(banner)},,{label}")

    # The banner: the first frame IS the in-feed thumbnail, so a bold top-of-screen title is
    # the biggest free CTR lever. Drawn on Layer 1 (top); the captions sit at the bottom.
    if banner:
        lines.append(f"Dialogue: 1,{_format_ts(0)},{_format_ts(banner_end)},Hook,,0,0,0,,{banner}")

    # Sparse on-screen key-point cards (middle of frame), after the banner. Off by default
    # since stage 4b: the key number replaces them (design 11.5).
    if key_points and config.get_bool("ENABLE_TEXT_CARDS", False):
        dur = total_dur if total_dur else (words[-1][1] if words else 0.0)
        start_after = banner_end
        card_dur = float(config.get("CARD_SECONDS", "1.8"))
        for cs, ce, text in _card_events(key_points, dur, start_after, card_dur, words):
            banner = _hook_banner_text(text, max_chars=18, max_lines=2, base_size=90)
            if banner:
                lines.append(f"Dialogue: 2,{_format_ts(cs)},{_format_ts(ce)},Card,,0,0,0,,{banner}")

    # One key number, large in the upper middle, while the narration says it (design 11.5).
    if number:
        start, end, label = number
        lines.append(f"Dialogue: 2,{_format_ts(start)},{_format_ts(end)},Number,,0,0,0,,{label}")

    # Group words into short phrases; each phrase is ONE karaoke line whose words fill to the
    # highlight colour exactly as spoken (active-word highlight — a retention driver).
    size = max(1, int(config.get("CAPTION_WORDS", "3")))
    groups = _caption_groups(words, size)
    for gi, chunk in enumerate(groups):
        start, end = chunk[0][0], chunk[-1][1]
        # Hold the caption to the next one across a short gap: dropping it for a breath between
        # phrases made the captions blink. The 'no blank frame' rule lived only in
        # _build_events, which production never calls. A real pause (over HOLD_GAP) still clears.
        if gi + 1 < len(groups):
            nxt = groups[gi + 1][0][0]
            if 0 < nxt - end <= _HOLD_GAP:
                end = nxt
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


def _burn(video_path: str, ass_path: str, out_path: str,
          cards: list[tuple[float, float, str]] | None = None, fps: int = 30) -> None:
    """Burn the .ass onto the video with FFmpeg. Runs in the subtitle's dir so the filter
    arg is a bare filename — avoids Windows drive-colon/backslash escaping in libass.

    `cards` are PIL stat-card PNGs composited centre-frame for their window. Each is a `-loop 1`
    still (so it exists at its timestamps, mirroring assembly's brand-bug pattern) gated by
    `enable='between(t,...)'`; `-shortest` keeps those infinite inputs from extending the reel.
    `fps` is the reel's own rate: the output keeps it, with a keyframe every half second."""
    work_dir = os.path.dirname(os.path.abspath(ass_path))
    _stage_font(work_dir)  # so libass resolves CAPTION_FONT via a relative fontsdir
    cards = cards or []

    cmd = [_ffmpeg(), "-y", "-i", os.path.abspath(video_path)]
    for _cs, _ce, png in cards:
        cmd += ["-loop", "1", "-i", os.path.basename(png)]  # basename + cwd: no path escaping

    if not cards:
        cmd += ["-vf", f"ass={os.path.basename(ass_path)}:fontsdir=.,{BT709_TAGS}"]
    else:
        parts = [f"[0:v]ass={os.path.basename(ass_path)}:fontsdir=.,{BT709_TAGS}[base]"]
        label = "[base]"
        for i, (cs, ce, _png) in enumerate(cards, start=1):
            nxt = f"[c{i}]"
            parts.append(f"{label}[{i}:v]overlay=(W-w)/2:(H-h)/2"
                         f":enable='between(t,{cs:.3f},{ce:.3f})'{nxt}")
            label = nxt
        cmd += ["-filter_complex", ";".join(parts), "-map", label, "-map", "0:a?", "-shortest"]

    cmd += [
        "-c:a", "copy",
        *x264_args(final=True, fps=fps),
        "-movflags", "+faststart",
        os.path.abspath(out_path),
    ]
    try:
        proc = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True,
                              timeout=RENDER_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"subtitles: ffmpeg burn timed out after {RENDER_TIMEOUT_SECONDS} s") from e
    if proc.returncode != 0:
        raise RuntimeError(f"subtitles: ffmpeg burn failed ({proc.returncode}):\n{proc.stderr[-1500:]}")


def burn_captions(video_path: str, audio_path: str, out_path: str,
                  hook_text: str | None = None, key_points: list[str] | None = None,
                  source_label: str | None = None, script_text: str | None = None,
                  fps: int = 30, key_number: str | None = None) -> str:
    """Transcribe → word-by-word events → burn into video. Return final reel path.

    `hook_text` (the punchy video title) is drawn as a bold banner on frame 1 — the first frame
    is the in-feed thumbnail, so this is the biggest free CTR lever. `key_points` are short
    phrases burned as sparse mid-frame cards (story-specific text). Both optional/back-compatible.

    With ENABLE_GRAPHIC_CARDS the key points render as PIL stat-card PNGs overlaid on the video
    instead of ASS text; if that render or its filtergraph fails we fall back to the ASS cards,
    so the styled-card path can never cost us a reel (rules 11, 14).

    `script_text` (the narration as written) supplies the caption WORDS; whisper supplies only
    their timing (see _align_to_script).
    """
    if not os.path.exists(video_path):
        raise ValueError(f"subtitles: video not found: {video_path}")
    if not os.path.exists(audio_path):
        raise ValueError(f"subtitles: audio not found: {audio_path}")

    words = _cached_words(audio_path)
    if not words:
        raise RuntimeError("subtitles: transcription produced no words — cannot caption reel.")
    words = _align_to_script(words, script_text)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    digest = hashlib.sha1(os.path.abspath(audio_path).encode("utf-8")).hexdigest()[:12]
    total_dur = words[-1][1] if words else None

    cards = _render_graphic_cards(key_points, total_dur or 0.0, out_dir)
    first_end = _first_sentence_end(words, script_text)
    number = _number_card(key_number, _number_moment_words(key_number, words), total_dur or 0.0)

    # The ASS omits text cards only when PNG cards will draw them, so they never double up.
    ass_path = os.path.join(out_dir, f"captions_{digest}.ass")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(_build_ass(words, hook_text, None if cards else key_points, total_dur, source_label,
                           first_end=first_end, number=number))

    fallback_ass = None
    if cards:  # a full-featured fallback: same captions, cards back as ASS text
        fallback_ass = os.path.join(out_dir, f"captions_{digest}_text.ass")
        with open(fallback_ass, "w", encoding="utf-8") as f:
            f.write(_build_ass(words, hook_text, key_points, total_dur, source_label,
                               first_end=first_end, number=number))

    log.info("subtitles: burning %d word events into %s (graphic cards=%d)",
             len(words), out_path, len(cards))
    try:
        _burn(video_path, ass_path, out_path, cards=cards, fps=fps)
    except RuntimeError:
        if not fallback_ass:
            raise
        log.warning("subtitles: card-overlay burn failed; retrying with ASS text cards.")
        _burn(video_path, fallback_ass, out_path, cards=None, fps=fps)

    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError("subtitles: ffmpeg reported success but produced no output file.")
    return out_path


# --- Hinglish reels: English subtitles timed from the narration (design 7.7) -----------------
# No speech recognition here: on test 4's narration Whisper invented English (a different
# invention each run). The sentence ends come from the narration's own pauses instead.

# The detector settings test 4's sentence ends were placed with (2026-11-10).
_PAUSE_FILTER = "silencedetect=noise=-38dB:d=0.12"
# A boundary that is not at a pause costs this much share error, so a pause is taken only when it
# lies within about 6% of the narration of where the characters put the end (1.6 s of 27 s). At
# 0.25 a real end with no pause was pulled to a breath 2.5 s away; test 4's ends are unchanged
# at 0.06 (final review, 2026-11-12).
_ESTIMATE_COST = 0.06
_MIN_SENTENCE_SECONDS = 0.5
# A part boundary moves to a pause this close (seconds).
_PART_SNAP_SECONDS = 0.3


def _audio_seconds(path: str) -> float:
    try:
        import wave

        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:  # noqa: BLE001 — not a WAV: ask ffprobe
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", path],
                             capture_output=True, text=True, timeout=60).stdout
        return float(out.strip())


def pauses(audio_path: str) -> list[tuple[float, float]]:
    """The narration's pauses as (start, end) seconds, from FFmpeg's silencedetect. [] when they
    cannot be read: the subtitles then fall back to the character-share estimates (rule 14)."""
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", audio_path,
                              "-af", _PAUSE_FILTER, "-f", "null", "-"],
                             capture_output=True, text=True, timeout=60).stderr
    except Exception as e:  # noqa: BLE001 — estimate timing beats a lost reel
        log.warning("subtitles: could not read the narration's pauses (%s); timing by estimate", e)
        return []
    starts = [max(0.0, float(x)) for x in re.findall(r"silence_start: (-?[\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    if len(ends) < len(starts):  # a pause running to the end of the file has no end line
        ends.append(_audio_seconds(audio_path))
    return list(zip(starts, ends))


def _speech_span(pause_list: list[tuple[float, float]], duration: float) -> tuple[float, float]:
    """When speech starts (after a leading pause) and ends (at a trailing one)."""
    t0 = next((e for s, e in pause_list if s <= 0.05), 0.0)
    t1 = next((s for s, e in pause_list if e >= duration - 0.05 and s > t0), duration)
    return t0, t1


def sentence_ends(pause_list: list[tuple[float, float]], weights: list[int],
                  duration: float) -> list[float]:
    """When each sentence ends: every end but the last at a pause's middle, chosen for all the
    sentences together, in order, so each sentence's share of the spoken characters (`weights`)
    stays as close as possible to its share of the time (design 7.7). This global assignment
    placed 5 of 5 ends on both test narrations, where snapping each estimate to its nearest
    pause missed 2 of 5. With too few pauses an end falls back to its estimate; every sentence
    keeps at least half a second."""
    n = len(weights)
    t0, t1 = _speech_span(pause_list, duration)
    if n <= 1:
        return [t1] * n
    span = max(t1 - t0, 1e-6)
    inner = [(s + e) / 2 for s, e in pause_list if s > t0 + 0.05 and e < t1 - 0.05]
    total = float(sum(weights)) or 1.0
    shares = [sum(weights[:k + 1]) / total for k in range(n - 1)]
    cands = [sorted([(t, abs((t - t0) / span - share)) for t in inner]
                    + [(t0 + share * span, _ESTIMATE_COST)]) for share in shares]
    inf = float("inf")
    best = [[(inf, -1)] * len(c) for c in cands]
    for j, (t, cost) in enumerate(cands[0]):
        if t - t0 >= _MIN_SENTENCE_SECONDS:
            best[0][j] = (cost, -1)
    for k in range(1, n - 1):
        for j, (t, cost) in enumerate(cands[k]):
            for i, (prev, _c) in enumerate(cands[k - 1]):
                total_cost = best[k - 1][i][0] + cost
                if t - prev >= _MIN_SENTENCE_SECONDS and total_cost < best[k][j][0]:
                    best[k][j] = (total_cost, i)
    last = [j for j, (t, _c) in enumerate(cands[-1])
            if best[-1][j][0] < inf and t1 - t >= _MIN_SENTENCE_SECONDS]
    if not last:  # too short a narration for its sentences: share the time by characters
        return [t0 + share * span for share in shares] + [t1]
    j = min(last, key=lambda x: best[-1][x][0])
    times = []
    for k in range(n - 2, -1, -1):
        times.append(cands[k][j][0])
        j = best[k][j][1]
    return times[::-1] + [t1]


def _spoken_chars(text: str) -> int:
    from src import hinglish

    return max(1, len(re.sub(r"\s+", "", hinglish.say_numbers(text or ""))))


def _usable_parts(line: dict) -> list[dict] | None:
    """The renderer's parts when they can be trusted: their Hinglish joins to the line's, their
    English uses only the sentence's own words, and together they carry all its numbers and
    names. None means the whole sentence shows instead."""
    from src import hinglish

    parts = [p for p in line.get("parts") or [] if p.get("hi") and p.get("en")]
    if not parts:
        return None
    joined_hi = re.sub(r"\s+", " ", " ".join(p["hi"] for p in parts)).strip()
    if joined_hi != re.sub(r"\s+", " ", line.get("hi") or "").strip():
        return None
    en = line.get("en") or ""
    joined_en = " ".join(p["en"] for p in parts)

    def words(text: str) -> Counter:
        return Counter(re.findall(r"[a-z0-9']+", text.lower().replace("’", "'")))

    # Exactly the sentence's own words, regrouped (design 7.7): a subset let "did not" vanish,
    # and the screen read "The court in 2024 / ban the film" for "did not ban". Equal words also
    # carry every number and name.
    if words(joined_en) != words(en):
        return None
    if not hinglish.numbers_in(en) <= hinglish.numbers_in(joined_en):
        return None
    return parts


def _sub_width(text: str) -> float:
    return _caption_px(text) * _SUB_PX / _KARAOKE_PX


def _sub_rows(text: str) -> list[str]:
    """Wrapped to the safe width, with no single word left alone on the last row."""
    rows = _wrap_px(text.split())
    if len(rows) >= 2 and len(rows[-1].split()) == 1 and len(rows[-2].split()) >= 3:
        head = rows[-2].split()
        rows[-2], rows[-1] = " ".join(head[:-1]), f"{head[-1]} {rows[-1]}"
    return rows


def _wrap_px(words: list[str]) -> list[str]:
    rows, cur = [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if cur and _sub_width(trial) > _MAX_CAPTION_PX:
            rows.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        rows.append(cur)
    return rows


def _fit(start: float, end: float, text: str) -> list[tuple[float, float, str]]:
    """One block if it fits in two rows; else halves by characters, each with its share of the
    time."""
    words = text.split()
    if len(_sub_rows(text)) <= 2 or len(words) < 2:
        return [(start, end, text)]
    total = sum(len(w) + 1 for w in words)
    acc, cut = 0, 1
    for k, w in enumerate(words):
        acc += len(w) + 1
        if acc >= total / 2:
            cut = max(1, min(len(words) - 1, k + 1))
            break
    head, tail = " ".join(words[:cut]), " ".join(words[cut:])
    mid = start + (end - start) * (len(head) + 1) / (total or 1)
    return _fit(start, mid, head) + _fit(mid, end, tail)


def _part_blocks(parts: list[dict], start: float, end: float,
                 pause_list: list[tuple[float, float]]) -> list[tuple[float, float, str]]:
    """One block per part, in spoken order, each boundary at the parts' share of the spoken
    characters, moved to a pause within 0.3 s."""
    chars = [_spoken_chars(p["hi"]) for p in parts]
    total = float(sum(chars))
    mids = [(s + e) / 2 for s, e in pause_list if start < s and e < end]
    times = [start]
    acc = 0
    for c in chars[:-1]:
        acc += c
        t = start + (end - start) * acc / total
        near = min(mids, key=lambda m: abs(m - t), default=None)
        if near is not None and abs(near - t) <= _PART_SNAP_SECONDS:
            t = near
        times.append(max(t, times[-1] + 0.2))
    times.append(end)
    out = []
    for i, part in enumerate(parts):
        out += _fit(times[i], times[i + 1], part["en"])
    return out


def _line_weights(lines: list[dict]) -> list[int]:
    """Each Hinglish line's share of the narration: its spoken characters."""
    return [_spoken_chars(line.get("said") or line.get("hi") or "") for line in lines]


def subtitle_blocks(lines: list[dict], pause_list: list[tuple[float, float]],
                    duration: float) -> list[tuple[float, float, str]]:
    """(start, end, English text) for every subtitle block of a Hinglish narration: the lines'
    sentence times from the pauses, then each line's parts in spoken order, or the whole
    sentence when its parts cannot be trusted."""
    ends = sentence_ends(pause_list, _line_weights(lines), duration)
    t0, _t1 = _speech_span(pause_list, duration)
    starts = [t0] + ends[:-1]
    blocks: list[tuple[float, float, str]] = []
    for line, start, end in zip(lines, starts, ends):
        parts = _usable_parts(line)
        if parts:
            blocks += _part_blocks(parts, start, end, pause_list)
        else:
            if line.get("parts"):
                log.info("subtitles: line %r's parts do not match it; showing the whole sentence",
                         (line.get("en") or "")[:60])
            blocks += _fit(start, end, line.get("en") or "")
    return blocks


def _hinglish_ass(blocks: list[tuple[float, float, str]], hook_text: str | None,
                  duration: float, source_label: str | None,
                  first_end: float | None = None,
                  number: tuple[float, float, str] | None = None) -> str:
    """The banner and the source line as on every reel (held for line 1, `first_end`), then
    the English blocks: plain white, at most two rows each, each held until the next starts."""
    lines = [_build_ass([], hook_text, None, duration, source_label,
                        first_end=first_end, number=number).rstrip("\n")]
    for i, (start, end, text) in enumerate(blocks):
        until = blocks[i + 1][0] if i + 1 < len(blocks) else max(end, duration)
        rows = [_ass_escape(_NON_RENDERABLE.sub("", row)) for row in _sub_rows(text)]
        lines.append(f"Dialogue: 0,{_format_ts(start)},{_format_ts(until)},Sub,,0,0,0,,"
                     + "\\N".join(r for r in rows if r))
    return "\n".join(lines) + "\n"


def burn_hinglish(video_path: str, audio_path: str, out_path: str, lines: list[dict],
                  hook_text: str | None = None, source_label: str | None = None,
                  fps: int = 30, key_number: str | None = None) -> str:
    """Burn English subtitles for a Hinglish narration: no speech recognition; the timing comes
    from the narration's pauses and the text from the checked lines (design 7.7)."""
    if not os.path.exists(video_path):
        raise ValueError(f"subtitles: video not found: {video_path}")
    if not os.path.exists(audio_path):
        raise ValueError(f"subtitles: audio not found: {audio_path}")
    duration = _audio_seconds(audio_path)
    pause_list = pauses(audio_path)
    blocks = subtitle_blocks(lines, pause_list, duration)
    first_end = sentence_ends(pause_list, _line_weights(lines), duration)[0] if lines else None
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    digest = hashlib.sha1(os.path.abspath(audio_path).encode("utf-8")).hexdigest()[:12]
    ass_path = os.path.join(out_dir, f"subs_{digest}.ass")
    with open(ass_path, "w", encoding="utf-8") as f:
        number = _number_card(key_number, _number_moment_blocks(key_number, blocks), duration)
        f.write(_hinglish_ass(blocks, hook_text, duration, source_label, first_end, number))
    log.info("subtitles: burning %d English blocks for a Hinglish narration into %s",
             len(blocks), out_path)
    _burn(video_path, ass_path, out_path, fps=fps)
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError("subtitles: ffmpeg reported success but produced no output file.")
    return out_path


# --- The preflight: the burn is tested before any clip is bought (design 6.2 step 1) ----------
# PyAV 19 broke the caption step on 2026-10-01 and nothing was published for 8 days. With paid
# clips in the reel, every reel of such a run would have bought its clips and then failed here.

_WORDS: dict[tuple, list] = {}  # one narration's transcription, shared by the preflight and burn


def _cached_words(audio_path: str) -> list[tuple[float, float, str]]:
    """The narration's timed words, transcribed once per file (path, size and mtime)."""
    st = os.stat(audio_path)
    key = (os.path.abspath(audio_path), st.st_size, st.st_mtime_ns)
    if key not in _WORDS:
        words = _transcribe_words(audio_path)
        _WORDS.clear()
        _WORDS[key] = words
    return _WORDS[key]


def _blank_clip(out_dir: str) -> str:
    """One second of black 1080x1920 at 24 fps with silent audio, to burn the subtitles onto."""
    path = os.path.join(out_dir, "preflight_blank.mp4")
    subprocess.run([_ffmpeg(), "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=24:d=1",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "1", "-c:v", "libx264",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", path],
                   check=True, capture_output=True, timeout=RENDER_TIMEOUT_SECONDS)
    return path


def preflight(audio_path: str, out_dir: str, *, lines: list[dict] | None = None,
              hook_text: str | None = None, source_label: str | None = None) -> bool:
    """True when the reel's own subtitle file burns onto a one-second blank clip. Never raises.

    `lines` are a Hinglish narration's checked lines; without them the narration is English, and
    it is transcribed first, which is the step that broke in October (`burn_captions` then reuses
    the words). False means nothing is bought for the reel: it would fail at its captions after
    paying for its clips."""
    try:
        os.makedirs(out_dir, exist_ok=True)
        if lines:
            duration = _audio_seconds(audio_path)
            ass = _hinglish_ass(subtitle_blocks(lines, pauses(audio_path), duration), hook_text,
                                duration, source_label)
        else:
            words = _cached_words(audio_path)
            if not words:
                raise RuntimeError("the transcription produced no words")
            ass = _build_ass(words, hook_text, None, words[-1][1], source_label)
        ass_path = os.path.join(out_dir, "preflight.ass")
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass)
        out = os.path.join(out_dir, "preflight.mp4")
        _burn(_blank_clip(out_dir), ass_path, out, fps=24)
        if not (os.path.exists(out) and os.path.getsize(out) > 0):
            raise RuntimeError("the burn produced no file")
    except Exception as e:  # noqa: BLE001 — a failed test is an answer, not a crash
        log.warning("subtitles: the preflight burn failed (%s); no clips are bought for this reel",
                    e)
        return False
    return True
