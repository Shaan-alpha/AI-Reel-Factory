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
import logging
import os
import re
import shutil
import subprocess
import tempfile

from PIL import Image, ImageStat

from src import config

log = logging.getLogger(__name__)

TEXT_CONFIDENCE = 70   # a word read at this confidence or more is lettering (design 11.6)
TEXT_LETTERS = 3       # ...when it has at least this many letters
DARK_BELOW = 60        # mean brightness (0-255) of the middle half; clean stills measured 83+
BAR_MEAN = 16          # letterbox bars: the top and bottom sixteenths both this dark...
BAR_STDDEV = 6         # ...and this flat

_OCR_TIMEOUT = 60
_WINDOWS_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
_warned_no_tesseract = False


# --- Stills ------------------------------------------------------------------------------------

def _tesseract() -> str | None:
    """The Tesseract binary: TESSERACT_BINARY, then PATH, then the Windows installer's place."""
    cand = config.get("TESSERACT_BINARY") or shutil.which("tesseract")
    if cand:
        return cand
    return _WINDOWS_TESSERACT if os.path.exists(_WINDOWS_TESSERACT) else None


def _read(binary: str, path: str) -> list[tuple[str, float]]:
    """One Tesseract reading (sparse text, TSV): the words of 3+ letters and their confidence.
    The output is UTF-8 whatever the console's code page."""
    out = subprocess.run([binary, path, "stdout", "--psm", "11", "tsv"], capture_output=True,
                         timeout=_OCR_TIMEOUT).stdout
    text = out.decode("utf-8", "replace") if isinstance(out, bytes) else str(out or "")
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
