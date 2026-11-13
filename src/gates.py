"""Automatic picture checks (design 11.6): nothing looks at a reel before it is public, so these
do. A still with lettering, too dark or letterboxed is redrawn by its caller; a broken clip
becomes a still; a broken reel is not uploaded.

Each check returns a plain list of problems, empty when the picture passes, and never raises: a
check that cannot run is skipped with a warning (rule 14), so a gate never costs a reel on its
own failure. Tesseract and FFmpeg are called as binaries, each with a timeout.

Calibrated on 2026-11-13 (STATUS.md): FLUX writes gibberish, and Tesseract's confidence falls on
non-words, so the still is read twice, as drawn and as a grayscale copy at twice the size."""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from PIL import Image, ImageStat

from src import assembly, config

log = logging.getLogger(__name__)

TEXT_CONFIDENCE = 70   # a word read at this confidence or more is lettering (design 11.6)
TEXT_LETTERS = 3       # ...when it has at least this many letters
DARK_BELOW = 60        # mean brightness (0-255) of the middle half; clean stills measured 83+
BAR_MEAN = 16          # letterbox bars: the top and bottom sixteenths both this dark...
BAR_STDDEV = 6         # ...and this flat
CLIP_MIN_SECONDS = 4.5  # a clip's floor (design 11.6); it must also cover its whole shot
CLIP_BLACK = 0.5       # a clip's black stretch this long or longer fails it
CLIP_FROZEN = 1.5      # ...and a frozen one
REEL_SLACK = 0.2       # a finished reel's length may differ from its narration's by this much
REEL_BLACK = 1.0       # a finished reel's black stretch this long or longer fails it
REEL_FROZEN = 2.0      # ...and a frozen one

_OCR_TIMEOUT = 60
_DETECT_TIMEOUT = 120
_WINDOWS_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
_warned_no_tesseract = False


# --- Stills ------------------------------------------------------------------------------------

def _tesseract() -> str | None:
    """The Tesseract binary: TESSERACT_BINARY, then PATH, then the Windows installer's place."""
    cand = config.get("TESSERACT_BINARY") or shutil.which("tesseract")
    if cand:
        return cand
    return _WINDOWS_TESSERACT if os.path.exists(_WINDOWS_TESSERACT) else None


def _text(data) -> str:
    """A subprocess stream as text: UTF-8 whatever the console's code page."""
    return data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data or "")


def _read(binary: str, path: str) -> list[tuple[str, float]]:
    """One Tesseract reading (sparse text, TSV): the words of 3+ letters and their confidence.
    Raises when Tesseract fails or prints no TSV (missing language data exits 1 with a bare
    header), so a broken install is a warning, never a run of clean-looking stills."""
    proc = subprocess.run([binary, path, "stdout", "--psm", "11", "tsv"], capture_output=True,
                          timeout=_OCR_TIMEOUT)
    text = _text(proc.stdout)
    if proc.returncode != 0:
        why = _text(getattr(proc, "stderr", b"")).strip()[:200]
        raise RuntimeError(f"tesseract exited {proc.returncode}: {why}")
    if "conf" not in text.split("\n", 1)[0]:
        raise RuntimeError("tesseract printed no TSV")
    words = []
    for row in csv.DictReader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE):
        word = (row.get("text") or "").strip()
        try:
            conf = float(row.get("conf") or -1)
        except ValueError:
            continue
        if conf >= 0 and len(re.sub(r"[^A-Za-z]", "", word)) >= TEXT_LETTERS:
            words.append((word, conf))
    return words


def _ocr_words(path: str) -> list[tuple[str, float]] | None:
    """Words read from the still and from a grayscale 2x copy of it; None without Tesseract.
    A reading that fails or times out is skipped with a warning."""
    global _warned_no_tesseract
    binary = _tesseract()
    if binary is None:
        if not _warned_no_tesseract:
            log.warning("gates: no Tesseract binary (install tesseract-ocr or set "
                        "TESSERACT_BINARY); the stills' text check is skipped")
            _warned_no_tesseract = True
        return None
    words: list[tuple[str, float]] = []
    with tempfile.TemporaryDirectory() as tmp:
        doubled = os.path.join(tmp, "still_ocr2x.png")
        try:
            with Image.open(path) as img:
                gray = img.convert("L")
            gray.resize((gray.width * 2, gray.height * 2), Image.LANCZOS).save(doubled)
        except Exception as e:  # noqa: BLE001 — the original is still read
            log.warning("gates: no 2x copy of %s (%s)", os.path.basename(path), e)
            doubled = None
        for source in (path, doubled):
            if source is None:
                continue
            try:
                words += _read(binary, source)
            except Exception as e:  # noqa: BLE001 — a hung or crashed reading is skipped
                log.warning("gates: Tesseract could not read %s (%s: %s)",
                            os.path.basename(path), type(e).__name__, e)
    return words


def still_problems(path: str) -> list[str]:
    """What is wrong with a still, one entry per failed check: "text: ..." (every word read at
    TEXT_CONFIDENCE or more), "dark: ...", "letterbox bars", or "unreadable: ...". Empty when it
    passes."""
    try:
        with Image.open(path) as img:
            gray = img.convert("L")
    except Exception as e:  # noqa: BLE001
        return [f"unreadable: {type(e).__name__}: {e}"]
    problems = []
    hits = [(w, c) for w, c in (_ocr_words(path) or []) if c >= TEXT_CONFIDENCE]
    if hits:
        problems.append("text: " + ", ".join(f"{w!r} {c:.0f}" for w, c in hits[:8]))
    w, h = gray.size
    middle = ImageStat.Stat(gray.crop((w // 4, h // 4, w - w // 4, h - h // 4))).mean[0]
    if middle < DARK_BELOW:
        problems.append(f"dark: {middle:.0f} < {DARK_BELOW}")
    band = max(1, h // 16)
    edges = [ImageStat.Stat(gray.crop(box)) for box in ((0, 0, w, band), (0, h - band, w, h))]
    if all(s.mean[0] < BAR_MEAN and s.stddev[0] < BAR_STDDEV for s in edges):
        problems.append("letterbox bars")
    return problems


# --- Clips and reels -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Media:
    """What ffprobe says about a file."""

    duration: float
    video: bool
    audio: bool


def _probe(path: str) -> Media:
    """One ffprobe call; raises when the file cannot be read."""
    out = subprocess.run([assembly._ffprobe(), "-v", "error", "-show_entries",
                          "format=duration:stream=codec_type", "-of", "json", path],
                         capture_output=True, check=True,
                         timeout=assembly.PROBE_TIMEOUT_SECONDS).stdout
    data = json.loads(out.decode("utf-8", "replace") if isinstance(out, bytes) else out)
    kinds = {stream.get("codec_type") for stream in data.get("streams") or []}
    return Media(float(data["format"]["duration"]), "video" in kinds, "audio" in kinds)


_BLACK = re.compile(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)")
_FREEZE_START = re.compile(r"freeze_start:\s*([\d.]+)")
_FREEZE_END = re.compile(r"freeze_end:\s*([\d.]+)")


def _stretches(path: str, black_min: float, frozen_min: float,
               duration: float) -> tuple[list[float], list[float]]:
    """The lengths of the black stretches (at least black_min) and the frozen ones (at least
    frozen_min), from one FFmpeg pass. A freeze still running at the end has no end in the log:
    it lasts to `duration`."""
    proc = subprocess.run([assembly._ffmpeg(), "-hide_banner", "-nostats", "-i", path, "-vf",
                           f"blackdetect=d={black_min}:pix_th=0.10,"
                           f"freezedetect=n=-60dB:d={frozen_min}",
                           "-an", "-f", "null", "-"], capture_output=True,
                          timeout=_DETECT_TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg exited {proc.returncode}")
    err = proc.stderr
    log_text = err.decode("utf-8", "replace") if isinstance(err, bytes) else str(err or "")
    black = [float(end) - float(start) for start, end in _BLACK.findall(log_text)]
    starts = [float(x) for x in _FREEZE_START.findall(log_text)]
    ends = [float(x) for x in _FREEZE_END.findall(log_text)]
    frozen = [(ends[i] if i < len(ends) else duration) - start for i, start in enumerate(starts)]
    return black, frozen


def _stretch_problems(path: str, black_min: float, frozen_min: float,
                      duration: float) -> list[str]:
    """The black and frozen stretches as problems; a pass that cannot run is skipped."""
    try:
        black, frozen = _stretches(path, black_min, frozen_min, duration)
    except Exception as e:  # noqa: BLE001 — a check that cannot run never costs the picture
        log.warning("gates: the black and frozen check could not run on %s (%s: %s); skipped",
                    os.path.basename(path), type(e).__name__, e)
        return []
    problems = []
    if black:
        problems.append("black: " + ", ".join(f"{d:.1f} s" for d in black))
    if frozen:
        problems.append("frozen: " + ", ".join(f"{d:.1f} s" for d in frozen))
    return problems


def clip_problems(path: str, seconds: float) -> list[str]:
    """What is wrong with a bought clip for a shot of `seconds` (design 11.6): unreadable, no
    video stream, shorter than 4.5 s or than its shot, a black stretch of 0.5 s or more, a
    frozen stretch of 1.5 s or more. Empty when it passes."""
    try:
        media = _probe(path)
    except Exception as e:  # noqa: BLE001
        return [f"unreadable: {type(e).__name__}: {e}"]
    if not media.video:
        return ["no video stream"]
    problems = []
    need = max(CLIP_MIN_SECONDS, seconds)
    if media.duration + 1e-3 < need:
        problems.append(f"short: {media.duration:.2f} s < {need:.2f} s")
    return problems + _stretch_problems(path, CLIP_BLACK, CLIP_FROZEN, media.duration)


def reel_problems(path: str, narration_seconds: float) -> list[str]:
    """What is wrong with a finished reel (design 11.6): unreadable, no video or no audio
    stream, a length more than 0.2 s off its narration's, a black stretch of 1.0 s or more, a
    frozen stretch of 2.0 s or more. Empty when it may be uploaded. Only a reel that cannot be
    probed is refused for the check's own sake; a detection pass that cannot run is skipped."""
    try:
        media = _probe(path)
    except Exception as e:  # noqa: BLE001
        return [f"unreadable: {type(e).__name__}: {e}"]
    problems = []
    if not media.video:
        problems.append("no video stream")
    if not media.audio:
        problems.append("no audio stream")
    if problems:
        return problems
    if abs(media.duration - narration_seconds) > REEL_SLACK:
        problems.append(f"length: {media.duration:.2f} s for {narration_seconds:.2f} s of "
                        f"narration")
    return problems + _stretch_problems(path, REEL_BLACK, REEL_FROZEN, media.duration)
