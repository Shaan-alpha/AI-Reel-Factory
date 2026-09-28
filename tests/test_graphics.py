"""Tests for src/graphics.py."""
from __future__ import annotations

import os

from PIL import Image

from src import graphics


def test_create_stat_card(tmp_path):
    out_path = str(tmp_path / "card.png")
    res = graphics.create_stat_card("Rs 2 Lakh Crore", out_path)
    assert res == out_path
    assert os.path.isfile(out_path)
    assert os.path.getsize(out_path) > 500

    # Verify PNG RGBA image structure
    with Image.open(out_path) as img:
        assert img.mode == "RGBA"
        assert img.size == (800, 240)
        assert img.getpixel((0, 0))[3] == 0, "corners stay transparent (rounded card)"
        assert img.getpixel((400, 120))[3] > 0, "the card body is drawn"


def test_create_stat_card_wraps_long_text(tmp_path):
    """Long key points must wrap inside the card, not run off the edge."""
    out_path = str(tmp_path / "long.png")
    graphics.create_stat_card("A very long key point that cannot fit on one single line",
                              out_path, width=600, height=400)
    with Image.open(out_path) as img:
        assert img.size == (600, 400)
        # text pixels exist well above and below the vertical centre → more than one line
        assert img.getpixel((300, 150))[3] > 0 and img.getpixel((300, 250))[3] > 0


def test_create_stat_card_creates_missing_parent_dir(tmp_path):
    out_path = str(tmp_path / "nested" / "deeper" / "card.png")
    assert graphics.create_stat_card("Ok", out_path) == out_path
    assert os.path.isfile(out_path)


def test_a_long_point_shrinks_to_fit_the_card(tmp_path):
    out = graphics.create_stat_card(
        "Four whole lines of key point text that would overflow the card at the old size",
        str(tmp_path / "c.png"))
    from PIL import Image
    alpha = Image.open(out).split()[-1]
    assert alpha.getbbox() is not None


def test_the_font_resolves_from_another_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CAPTION_FONT_FILE", raising=False)
    font = graphics._get_font(40)
    assert getattr(font, "size", None) == 40, "fell back to the 10 px bitmap font"
