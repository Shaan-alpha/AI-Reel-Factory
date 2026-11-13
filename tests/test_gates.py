"""The automatic picture checks (design 11.6): stills, clips and the finished reel."""
import logging
import subprocess
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw, ImageFont

from src import gates

W, H = 768, 1344
HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"


def _tsv(*words: tuple[str, float]) -> bytes:
    rows = [f"5\t1\t1\t1\t1\t{i}\t10\t10\t80\t30\t{conf}\t{text}\n"
            for i, (text, conf) in enumerate(words, 1)]
    return (HEADER + "1\t1\t0\t0\t0\t0\t0\t0\t768\t1344\t-1\t\n" + "".join(rows)).encode("utf-8")


def _still(tmp_path, name="still.jpg", fill=200, middle=None, bars=False) -> str:
    """A plain grey still; `middle` paints the middle half, `bars` blacks out the top and
    bottom quarters (letterbox)."""
    img = Image.new("L", (W, H), fill)
    draw = ImageDraw.Draw(img)
    if middle is not None:
        draw.rectangle((W // 4, H // 4, 3 * W // 4, 3 * H // 4), fill=middle)
    if bars:
        draw.rectangle((0, 0, W, H // 4), fill=0)
        draw.rectangle((0, 3 * H // 4, W, H), fill=0)
    path = tmp_path / name
    img.convert("RGB").save(path, quality=92)
    return str(path)


def _ocr(monkeypatch, original: bytes = b"", doubled: bytes = b"", raises=None) -> list:
    """Tesseract replaced: `original` is what it reads from the still itself, `doubled` from the
    2x copy. Returns the commands it was given."""
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if raises:
            raise raises
        out = doubled if "ocr2x" in cmd[1] else original
        return SimpleNamespace(stdout=out, returncode=0)

    monkeypatch.setattr(gates, "_tesseract", lambda: "tesseract")
    monkeypatch.setattr(gates.subprocess, "run", run)
    return calls


# --- Stills -----------------------------------------------------------------------------------

def test_a_word_read_at_70_is_text(monkeypatch, tmp_path):
    calls = _ocr(monkeypatch, original=_tsv(("TBEREOROIN", 90.2), ("ani", 59.0)))
    problems = gates.still_problems(_still(tmp_path))
    assert len(problems) == 1 and problems[0].startswith("text:")
    assert "TBEREOROIN" in problems[0] and "ani" not in problems[0]
    cmd, kwargs = calls[0]
    assert cmd[2:] == ["stdout", "--psm", "11", "tsv"] and kwargs["timeout"] == 60


def test_noise_under_70_is_not_text(monkeypatch, tmp_path):
    _ocr(monkeypatch, original=_tsv(("bel", 59.0), ("are", 68.0), ("OK", 95.0), ("A1", 99.0)))
    assert gates.still_problems(_still(tmp_path)) == []


def test_the_2x_copy_is_read_too(monkeypatch, tmp_path):
    """The render's caption read 46 from the still and 90 from a 2x copy (calibration)."""
    calls = _ocr(monkeypatch, original=_tsv(("EREORGC", 46.0)), doubled=_tsv(("BER", 90.0)))
    problems = gates.still_problems(_still(tmp_path))
    assert problems and problems[0].startswith("text:") and "BER" in problems[0]
    assert len(calls) == 2 and calls[1][0][1].endswith(".png")


def test_no_tesseract_skips_the_text_check_once(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(gates, "_tesseract", lambda: None)
    monkeypatch.setattr(gates, "_warned_no_tesseract", False)
    with caplog.at_level(logging.WARNING, logger="src.gates"):
        assert gates.still_problems(_still(tmp_path, "a.jpg")) == []
        assert gates.still_problems(_still(tmp_path, "b.jpg")) == []
    assert len([r for r in caplog.records if "Tesseract" in r.getMessage()]) == 1


def test_a_tesseract_timeout_skips_the_text_check(monkeypatch, tmp_path):
    """Review Focus 1: a hung Tesseract costs the still nothing but its text check."""
    _ocr(monkeypatch, raises=subprocess.TimeoutExpired(["tesseract"], 60))
    assert gates.still_problems(_still(tmp_path)) == []


def test_tsv_bytes_cp1252_cannot_read_are_replaced(monkeypatch, tmp_path):
    """Review Focus 5: Tesseract writes UTF-8; a Windows console decoding it crashed."""
    raw = _tsv(("WELCOME", 95.0)).replace(b"WELCOME", b"WEL\x9dCOME")
    _ocr(monkeypatch, original=raw)
    problems = gates.still_problems(_still(tmp_path))
    assert problems and problems[0].startswith("text:")


def test_a_dark_middle_is_dark(monkeypatch, tmp_path):
    _ocr(monkeypatch)
    assert gates.still_problems(_still(tmp_path, middle=30)) == ["dark: 30 < 60"]


def test_letterbox_bars_are_found(monkeypatch, tmp_path):
    _ocr(monkeypatch)
    assert gates.still_problems(_still(tmp_path, bars=True)) == ["letterbox bars"]


def test_a_dark_backdrop_is_not_bars(monkeypatch, tmp_path):
    """Clip 4's chip on a dark backdrop: top band 52, bottom 23, a bright subject."""
    _ocr(monkeypatch)
    img = Image.new("L", (W, H), 52)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, H // 2, W, H), fill=23)
    draw.rectangle((W // 4, H // 4, 3 * W // 4, 3 * H // 4), fill=150)
    path = tmp_path / "backdrop.jpg"
    img.convert("RGB").save(path, quality=92)
    assert gates.still_problems(str(path)) == []


def test_an_unreadable_still_is_a_problem(monkeypatch, tmp_path):
    _ocr(monkeypatch)
    path = tmp_path / "broken.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe0 not really a jpeg")
    problems = gates.still_problems(str(path))
    assert len(problems) == 1 and problems[0].startswith("unreadable:")


def test_real_tesseract_reads_lettering(tmp_path):
    """The binary itself, when there is one (CI installs tesseract-ocr): plain lettering is
    text, a smooth gradient is not."""
    if gates._tesseract() is None:
        pytest.skip("no Tesseract binary")
    img = Image.new("L", (W, H), 170)
    ImageDraw.Draw(img).text((60, 600), "WELCOME HOME", fill=20,
                             font=ImageFont.load_default(size=90))
    lettered = tmp_path / "lettered.jpg"
    img.convert("RGB").save(lettered, quality=92)
    problems = gates.still_problems(str(lettered))
    assert problems and problems[0].startswith("text:") and "WELCOME" in problems[0]

    gradient = Image.linear_gradient("L").resize((W, H)).point(lambda v: 90 + v // 2)
    smooth = tmp_path / "smooth.jpg"
    gradient.convert("RGB").save(smooth, quality=92)
    assert gates.still_problems(str(smooth)) == []
